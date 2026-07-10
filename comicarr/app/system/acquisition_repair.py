#  Copyright (C) 2025–2026 Comicarr contributors
#
#  This file is part of Comicarr.
#
#  Comicarr is free software: you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.

"""Durable, evidence-first acquisition reconciliation core.

This module intentionally has no HTTP, startup, or migration-completion
wiring.  It owns the database contract used by those adapters: read-only
preview, one-shot confirmation, an immutable ordered manifest, maintenance-
fenced NULL-safe compare-and-set apply, resumable checkpoints, and
conditional rollback.

The repair never infers explicit intent from the legacy ``Status`` column.
Only ``AcquisitionIntent`` is auditable intent.  In particular, migrated
``Status='Skipped'`` rows with NULL intent remain policy-controlled: verified
files are repaired to owned, released missing rows are optional Wanted
proposals, and future rows remain deferred.
"""

import datetime
import hashlib
import hmac
import json
import secrets
import time
import uuid
from pathlib import Path

from sqlalchemy import func, insert, or_, select, update
from sqlalchemy.exc import OperationalError

from comicarr.app.acquisition.maintenance import MaintenanceConflict, MaintenanceController
from comicarr.app.acquisition.models import AcquisitionIntent, Fulfillment
from comicarr.tables import (
    acquisition_repair_canaries,
    acquisition_repair_events,
    acquisition_repair_items,
    acquisition_repair_manifests,
    acquisition_repair_runs,
    acquisition_repair_series,
    annuals,
    comics,
    ddl_info,
    issues,
    nzblog,
    pipeline_journal,
    snatched,
)

MAX_JSON_BYTES = 256 * 1024
MAX_REASON_LENGTH = 255
WRITE_RETRY_LIMIT = 3
_OPEN_JOURNAL_STAGES = {"reserved", "snatched", "downloaded", "post_processing", "moved"}
_JOURNAL_EVIDENCE_STAGES = _OPEN_JOURNAL_STAGES | {"failed", "manual_review", "post_processed"}
_EXPLICIT_INTENTS = {
    AcquisitionIntent.WANTED.value,
    AcquisitionIntent.SKIPPED.value,
    AcquisitionIntent.IGNORED.value,
}
_INTENT_STATUS = {
    AcquisitionIntent.WANTED.value: "Wanted",
    AcquisitionIntent.SKIPPED.value: "Skipped",
    AcquisitionIntent.IGNORED.value: "Ignored",
}
_OWNED_STATUSES = {"Downloaded", "Archived"}
_SOURCE_TABLES = {"issue": issues, "annual": annuals}


class RepairError(RuntimeError):
    """Base class for durable acquisition repair failures."""


class RepairConfirmationError(RepairError):
    """The one-shot preview confirmation was invalid or stale."""


class RepairBlocked(RepairError):
    """The maintenance fence could not prove quiescence."""


def _now(value=None):
    value = value or datetime.datetime.now(datetime.timezone.utc)
    if value.tzinfo is None:
        value = value.replace(tzinfo=datetime.timezone.utc)
    return value.astimezone(datetime.timezone.utc)


def _iso(value=None):
    return _now(value).isoformat()


def _digest(value):
    return hashlib.sha256(str(value).encode("utf-8", "replace")).hexdigest()


def _json(value):
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)
    if len(encoded.encode("utf-8")) > MAX_JSON_BYTES:
        raise ValueError("repair manifest JSON exceeds %s bytes" % MAX_JSON_BYTES)
    return encoded


def _load(value):
    return json.loads(value) if value else {}


def _row_dict(row):
    return dict(row._mapping) if row is not None else None


def _reason(value):
    return str(value or "unspecified")[:MAX_REASON_LENGTH]


def _entity_key(entity_type, entity_id):
    return "%s:%s" % (entity_type, entity_id)


def _parse_entity_key(value):
    try:
        entity_type, entity_id = str(value).split(":", 1)
    except ValueError as e:
        raise RepairConfirmationError("invalid repair entity key") from e
    if entity_type not in _SOURCE_TABLES or not entity_id:
        raise RepairConfirmationError("invalid repair entity key")
    return entity_type, entity_id


def _parse_date(value):
    if value is None or not str(value).strip():
        return None
    try:
        return datetime.date.fromisoformat(str(value).strip()[:10])
    except (TypeError, ValueError):
        return None


def _selected_date(row):
    supplied = False
    for column, source in (
        ("ReleaseDate", "release_date"),
        ("DigitalDate", "digital_date"),
        ("IssueDate", "issue_date"),
    ):
        raw = row.get(column)
        supplied = supplied or bool(raw is not None and str(raw).strip())
        parsed = _parse_date(raw)
        if parsed is not None:
            return parsed, source, supplied
    return None, None, supplied


def _safe_verified_file(series, row):
    root = series.get("ComicLocation")
    location = row.get("Location")
    if not root or not location:
        return False
    try:
        root_path = Path(str(root)).expanduser().resolve(strict=True)
        raw = Path(str(location)).expanduser()
        candidate = raw if raw.is_absolute() else root_path / raw
        candidate = candidate.resolve(strict=True)
        return candidate.is_relative_to(root_path) and candidate.is_file()
    except (OSError, RuntimeError, ValueError):
        return False


def _source_before(row):
    # Store the complete source-row snapshot. Apply predicates every column,
    # including NULLs, so unrelated concurrent edits are visible conflicts.
    return dict(row)


def _preview_document(item):
    return {
        "sequence": item["sequence"],
        "entity_type": item["entity_type"],
        "entity_id": item["entity_id"],
        "series_id": item["series_id"],
        "intent": item["intent"],
        "fulfillment": item["fulfillment"],
        "reason": item["reason"],
        "date_source": item.get("date_source"),
        "selected_date": item.get("selected_date"),
        "evidence": item["evidence"],
        "before": item["before"],
        "proposed": item["proposed"],
        "optional": bool(item["optional"]),
        "selected": bool(item["selected"]),
    }


def _aggregate_document(series):
    return {
        "series_id": series["series_id"],
        "before_have": series.get("before_have"),
        "before_total": series.get("before_total"),
        "proposed_have": series.get("proposed_have"),
        "proposed_total": series.get("proposed_total"),
        "selected": bool(series.get("aggregate_selected")),
    }


def _fingerprint(items, series_documents=()):
    """Hash bounded canonical records incrementally.

    A library manifest can be much larger than the per-record JSON safety
    limit. Building one giant JSON value would turn that safety limit into an
    accidental maximum library size, so each independently bounded record is
    length-delimited into the digest instead.
    """

    digest = hashlib.sha256()
    for kind, documents in ((b"item", items), (b"series", series_documents)):
        for value in documents:
            document = _preview_document(value) if kind == b"item" else _aggregate_document(value)
            encoded = _json(document).encode("utf-8")
            digest.update(kind)
            digest.update(len(encoded).to_bytes(8, "big"))
            digest.update(encoded)
    return digest.hexdigest()


def _is_retryable_write_error(error):
    message = str(error).lower()
    return any(
        marker in message
        for marker in (
            "database is locked",
            "deadlock",
            "serialization failure",
            "could not serialize",
            "lock wait timeout",
        )
    )


class RepairService:
    """Persistence owner for series-scoped acquisition reconciliation."""

    def __init__(self, engine, maintenance=None):
        self.engine = engine
        self.maintenance = maintenance or MaintenanceController(engine)

    # ------------------------------------------------------------------
    # Read-only evidence preview
    # ------------------------------------------------------------------

    def _journal_evidence(self, conn, issue_id):
        rows = list(
            conn.execute(
                select(pipeline_journal)
                .where(pipeline_journal.c.issueid == str(issue_id))
                .where(pipeline_journal.c.stage.in_(tuple(_JOURNAL_EVIDENCE_STAGES)))
                .order_by(pipeline_journal.c.updated_date.desc(), pipeline_journal.c.stage_rank.desc())
            ).mappings()
        )
        if not rows:
            return None
        row = dict(rows[0])
        stage = str(row.get("stage") or "").lower()
        if stage == "failed":
            fulfillment = Fulfillment.FAILED
            reason = "journal_failed"
            target_status = "Failed"
        elif stage in {"manual_review", "post_processed"}:
            # A terminal quarantine must never fall through to the optional
            # Wanted rule. post_processed without verified file/archive
            # evidence is likewise conservative rather than assumed owned.
            fulfillment = Fulfillment.UNKNOWN
            reason = "journal_%s" % stage
            target_status = None
        elif stage == "reserved":
            fulfillment = Fulfillment.RESERVED
            reason = "journal_reserved"
            target_status = "Reserved"
        else:
            # downloaded/post_processing/moved mean the downloader accepted the
            # release but the owned-library fact is not yet fully committed.
            fulfillment = Fulfillment.SNATCHED
            reason = "journal_%s" % stage
            target_status = "Snatched"
        return {
            "fulfillment": fulfillment,
            "reason": reason,
            "target_status": target_status,
            "evidence": {
                "journal": True,
                "stage": stage,
                "release_key": row.get("release_key"),
                "provider": row.get("provider"),
            },
        }

    def _legacy_download_evidence(self, conn, issue_id):
        ddl_rows = list(
            conn.execute(select(ddl_info.c.ID, ddl_info.c.status).where(ddl_info.c.issueid == str(issue_id))).mappings()
        )
        statuses = {str(row.get("status") or "").strip().lower() for row in ddl_rows}
        if "failed" in statuses:
            return {
                "fulfillment": Fulfillment.FAILED,
                "reason": "legacy_ddl_failed",
                "target_status": "Failed",
                "evidence": {"ddl": True, "ddl_status": "Failed"},
            }
        if "downloading" in statuses:
            return {
                "fulfillment": Fulfillment.UNKNOWN,
                "reason": "legacy_ddl_downloading_unproven",
                "target_status": None,
                "evidence": {"ddl": True, "ddl_status": "Downloading"},
            }
        if statuses:
            return {
                "fulfillment": Fulfillment.UNKNOWN,
                "reason": "legacy_ddl_%s_unproven" % sorted(statuses)[0],
                "target_status": None,
                "evidence": {"ddl": True, "ddl_status": sorted(statuses)[0]},
            }

        legacy_snatch = conn.execute(
            select(snatched.c.Status).where(snatched.c.IssueID == str(issue_id)).limit(1)
        ).first()
        legacy_nzb = conn.execute(select(nzblog.c.IssueID).where(nzblog.c.IssueID == str(issue_id)).limit(1)).first()
        if legacy_snatch is not None or legacy_nzb is not None:
            return {
                "fulfillment": Fulfillment.UNKNOWN,
                "reason": "legacy_download_evidence_unproven",
                "target_status": None,
                "evidence": {"legacy_snatched": legacy_snatch is not None, "legacy_nzblog": legacy_nzb is not None},
            }
        return None

    def _project(self, conn, entity_type, row, series, today):
        issue_id = str(row["IssueID"])
        raw_intent = str(row.get("AcquisitionIntent") or "").strip().lower()
        intent = raw_intent if raw_intent in _EXPLICIT_INTENTS else AcquisitionIntent.POLICY.value
        current_status = row.get("Status")
        proposed = {}
        optional = False
        evidence = {
            "file_verified": False,
            "archive": False,
            "explicit_intent": intent in _EXPLICIT_INTENTS,
        }
        selected_date, date_source, date_was_supplied = _selected_date(row)

        # Fulfillment evidence and intent are orthogonal. File/archive and
        # pipeline/downloader evidence decide fulfillment; explicit intent is
        # retained alongside that state and only projects the compatibility
        # Status when no stronger operational evidence owns the Status value.
        if _safe_verified_file(series, row):
            fulfillment = Fulfillment.DOWNLOADED
            reason = "verified_file"
            evidence["file_verified"] = True
            if current_status != "Downloaded":
                proposed["Status"] = "Downloaded"
        elif current_status == "Archived":
            fulfillment = Fulfillment.ARCHIVED
            reason = "archived"
            evidence["archive"] = True
        else:
            journal = self._journal_evidence(conn, issue_id)
            if journal:
                fulfillment = journal["fulfillment"]
                reason = journal["reason"]
                evidence.update(journal["evidence"])
                if journal["target_status"] and current_status != journal["target_status"]:
                    proposed["Status"] = journal["target_status"]
            else:
                normalized_status = str(current_status or "").strip().lower()
                if normalized_status == "failed":
                    legacy = {
                        "fulfillment": Fulfillment.FAILED,
                        "reason": "legacy_status_failed",
                        "target_status": "Failed",
                        "evidence": {"legacy_status": "Failed"},
                    }
                elif normalized_status in {"snatched", "downloaded", "post-processed", "post_processed"}:
                    legacy = {
                        "fulfillment": Fulfillment.UNKNOWN,
                        "reason": "legacy_status_%s_unproven" % normalized_status.replace("-", "_"),
                        "target_status": None,
                        "evidence": {"legacy_status": current_status},
                    }
                else:
                    legacy = self._legacy_download_evidence(conn, issue_id)
                if legacy:
                    fulfillment = legacy["fulfillment"]
                    reason = legacy["reason"]
                    evidence.update(legacy["evidence"])
                    target = legacy["target_status"]
                    if target and current_status != target:
                        proposed["Status"] = target
                elif str(series.get("Status") or "").strip().lower() == "paused":
                    fulfillment = Fulfillment.MISSING
                    reason = "paused"
                elif selected_date is not None and selected_date > today:
                    fulfillment = Fulfillment.MISSING
                    reason = "future"
                elif selected_date is not None:
                    fulfillment = Fulfillment.MISSING
                    reason = "released_missing"
                elif date_was_supplied:
                    fulfillment = Fulfillment.UNKNOWN
                    reason = "invalid_date"
                else:
                    fulfillment = Fulfillment.UNKNOWN
                    reason = "missing_date"

                if legacy is None:
                    if intent in _EXPLICIT_INTENTS:
                        target = _INTENT_STATUS[intent]
                        if current_status != target:
                            proposed["Status"] = target
                    elif reason == "released_missing" and current_status != "Wanted":
                        # A legacy Skipped status is deliberately NOT explicit
                        # intent. Released missing policy rows are optional
                        # Wanted candidates, never automatic mutations.
                        proposed["Status"] = "Wanted"
                        optional = True

        item = {
            "entity_type": entity_type,
            "entity_id": issue_id,
            "series_id": str(row["ComicID"]),
            "intent": intent,
            "fulfillment": fulfillment.value,
            "reason": reason,
            "date_source": date_source,
            "selected_date": selected_date.isoformat() if selected_date else None,
            "evidence": evidence,
            "before": _source_before(row),
            "proposed": proposed,
            "optional": optional,
            "selected": bool(proposed) and not optional,
        }
        return item

    def _source_rows(self, conn, series_id):
        issue_rows = [
            ("issue", dict(row))
            for row in conn.execute(
                select(issues)
                .where(issues.c.ComicID == str(series_id))
                .order_by(issues.c.Int_IssueNumber, issues.c.Issue_Number, issues.c.IssueID)
            ).mappings()
        ]
        annual_rows = [
            ("annual", dict(row))
            for row in conn.execute(
                select(annuals)
                .where(annuals.c.ComicID == str(series_id))
                .where(or_(annuals.c.Deleted.is_(None), annuals.c.Deleted != 1))
                .order_by(annuals.c.Int_IssueNumber, annuals.c.Issue_Number, annuals.c.IssueID)
            ).mappings()
        ]
        # Stable cross-entity ordering. Issues precede annuals, while the order
        # within each table is explicit and independent of database row order.
        return issue_rows + annual_rows

    def _summary(self, items):
        summary = {
            "total": len(items),
            "owned": 0,
            "archived": 0,
            "in_flight": 0,
            "failed": 0,
            "optional_wanted": 0,
            "future": 0,
            "unknown": 0,
            "selected": sum(1 for item in items if item["selected"]),
        }
        for item in items:
            fulfillment = item["fulfillment"]
            if fulfillment == Fulfillment.DOWNLOADED.value:
                summary["owned"] += 1
            elif fulfillment == Fulfillment.ARCHIVED.value:
                summary["owned"] += 1
                summary["archived"] += 1
            elif fulfillment in {Fulfillment.RESERVED.value, Fulfillment.SNATCHED.value}:
                summary["in_flight"] += 1
            elif fulfillment == Fulfillment.FAILED.value:
                summary["failed"] += 1
            elif fulfillment == Fulfillment.UNKNOWN.value:
                summary["unknown"] += 1
            if item["optional"] and item["proposed"].get("Status") == "Wanted":
                summary["optional_wanted"] += 1
            if item["reason"] == "future":
                summary["future"] += 1
        return summary

    def preview_series(
        self,
        series_id,
        *,
        actor,
        session_id,
        today=None,
        now=None,
        token_ttl_seconds=900,
    ):
        if not actor or not session_id:
            raise ValueError("actor and session_id are required")
        today = today or datetime.date.today()
        created = _now(now)
        expires = created + datetime.timedelta(seconds=max(1, int(token_ttl_seconds)))
        run_id = str(uuid.uuid4())
        token = secrets.token_urlsafe(32)

        with self.engine.connect() as conn:
            series = conn.execute(select(comics).where(comics.c.ComicID == str(series_id))).mappings().first()
            if series is None:
                raise KeyError("unknown series %s" % series_id)
            series = dict(series)
            items = [
                self._project(conn, entity_type, row, series, today)
                for entity_type, row in self._source_rows(conn, series_id)
            ]

        for sequence, item in enumerate(items, start=1):
            item["sequence"] = sequence
        preview_fingerprint = _fingerprint(items)
        summary = self._summary(items)
        when = created.isoformat()

        with self.engine.begin() as conn:
            conn.execute(
                insert(acquisition_repair_runs).values(
                    run_id=run_id,
                    scope_type="series",
                    scope_id=str(series_id),
                    state="previewed",
                    actor_id=str(actor),
                    session_digest=_digest(session_id),
                    preview_token_digest=_digest(token),
                    token_expires_at=expires.isoformat(),
                    token_consumed_at=None,
                    preview_fingerprint=preview_fingerprint,
                    manifest_id=None,
                    maintenance_epoch=None,
                    item_count=len(items),
                    selected_count=summary["selected"],
                    applied_count=0,
                    conflict_count=0,
                    rollback_count=0,
                    rollback_conflict_count=0,
                    last_sequence=0,
                    created_at=when,
                    confirmed_at=None,
                    started_at=None,
                    updated_at=when,
                    completed_at=None,
                )
            )
            conn.execute(
                insert(acquisition_repair_series).values(
                    run_id=run_id,
                    series_id=str(series_id),
                    state="previewed",
                    dirty=0,
                    before_have=series.get("Have"),
                    before_total=series.get("Total"),
                    final_have=None,
                    final_total=None,
                    conflict_reason=None,
                    updated_at=when,
                )
            )
            for item in items:
                conn.execute(
                    insert(acquisition_repair_items).values(
                        run_id=run_id,
                        sequence=item["sequence"],
                        entity_type=item["entity_type"],
                        entity_id=item["entity_id"],
                        series_id=item["series_id"],
                        intent=item["intent"],
                        fulfillment=item["fulfillment"],
                        reason=item["reason"],
                        date_source=item["date_source"],
                        selected_date=item["selected_date"],
                        evidence_json=_json(item["evidence"]),
                        before_json=_json(item["before"]),
                        proposed_json=_json(item["proposed"]),
                        optional=int(item["optional"]),
                        selected=int(item["selected"]),
                        apply_state="pending",
                        apply_reason=None,
                        applied_json=None,
                        rollback_state="pending",
                        rollback_reason=None,
                        created_at=when,
                        updated_at=when,
                        applied_at=None,
                        rolled_back_at=None,
                    )
                )
            self._event(conn, run_id, "preview", actor, "series preview created")

        return {
            "run_id": run_id,
            "preview_token": token,
            "fingerprint": preview_fingerprint,
            "summary": summary,
            "items": [self._public_item(item) for item in items],
        }

    # ------------------------------------------------------------------
    # One-shot confirmation / manifest freeze
    # ------------------------------------------------------------------

    def _authorize(self, run, actor, session_id):
        if str(actor) != run["actor_id"]:
            raise RepairConfirmationError("repair is owned by a different actor")
        supplied = _digest(session_id)
        if not hmac.compare_digest(supplied, run["session_digest"]):
            raise RepairConfirmationError("repair is bound to a different session")

    def _db_item_document(self, row, *, selected=None):
        return {
            "sequence": row["sequence"],
            "entity_type": row["entity_type"],
            "entity_id": row["entity_id"],
            "series_id": row["series_id"],
            "intent": row["intent"],
            "fulfillment": row["fulfillment"],
            "reason": row["reason"],
            "date_source": row["date_source"],
            "selected_date": row["selected_date"],
            "evidence": _load(row["evidence_json"]),
            "before": _load(row["before_json"]),
            "proposed": _load(row["proposed_json"]),
            "optional": bool(row["optional"]),
            "selected": bool(row["selected"] if selected is None else selected),
        }

    def confirm(
        self,
        run_id,
        *,
        preview_token,
        fingerprint,
        actor,
        session_id,
        selected_optional_keys=(),
        canary_entity_key=None,
        now=None,
    ):
        selected_optional_keys = {str(value) for value in selected_optional_keys}
        confirmed_at = _now(now)
        supplied_token_digest = _digest(preview_token)
        manifest_id = str(uuid.uuid4())

        with self.engine.begin() as conn:
            run_row = (
                conn.execute(select(acquisition_repair_runs).where(acquisition_repair_runs.c.run_id == str(run_id)))
                .mappings()
                .first()
            )
            if run_row is None:
                raise RepairConfirmationError("unknown repair preview")
            run = dict(run_row)
            self._authorize(run, actor, session_id)
            if run["state"] != "previewed" or run["token_consumed_at"] is not None:
                raise RepairConfirmationError("preview token was consumed or manifest already confirmed")
            if confirmed_at > _now(datetime.datetime.fromisoformat(run["token_expires_at"])):
                raise RepairConfirmationError("preview token expired")
            if not hmac.compare_digest(supplied_token_digest, run["preview_token_digest"]):
                raise RepairConfirmationError("invalid preview token")
            if not hmac.compare_digest(str(fingerprint), run["preview_fingerprint"]):
                raise RepairConfirmationError("preview fingerprint changed")

            rows = [
                dict(row)
                for row in conn.execute(
                    select(acquisition_repair_items)
                    .where(acquisition_repair_items.c.run_id == str(run_id))
                    .order_by(acquisition_repair_items.c.sequence)
                ).mappings()
            ]
            optional_keys = {
                _entity_key(row["entity_type"], row["entity_id"])
                for row in rows
                if row["optional"] and _load(row["proposed_json"])
            }
            unexpected = selected_optional_keys - optional_keys
            if unexpected:
                raise RepairConfirmationError("selection includes a non-optional manifest item")

            documents = []
            selected_count = 0
            selected_keys = set()
            for row in rows:
                key = _entity_key(row["entity_type"], row["entity_id"])
                selected = bool(row["selected"]) or key in selected_optional_keys
                if selected:
                    selected_count += 1
                    selected_keys.add(key)
                documents.append(self._db_item_document(row, selected=selected))
                if selected != bool(row["selected"]):
                    conn.execute(
                        update(acquisition_repair_items)
                        .where(acquisition_repair_items.c.item_id == row["item_id"])
                        .values(selected=int(selected), updated_at=confirmed_at.isoformat())
                    )

            frozen_fingerprint = hashlib.sha256(_json(documents).encode("utf-8")).hexdigest()
            consumed = conn.execute(
                update(acquisition_repair_runs)
                .where(acquisition_repair_runs.c.run_id == str(run_id))
                .where(acquisition_repair_runs.c.state == "previewed")
                .where(acquisition_repair_runs.c.token_consumed_at.is_(None))
                .where(acquisition_repair_runs.c.preview_token_digest == supplied_token_digest)
                .values(
                    state="confirmed",
                    token_consumed_at=confirmed_at.isoformat(),
                    manifest_id=manifest_id,
                    selected_count=selected_count,
                    confirmed_at=confirmed_at.isoformat(),
                    updated_at=confirmed_at.isoformat(),
                )
            )
            if consumed.rowcount != 1:
                raise RepairConfirmationError("preview token was consumed concurrently")
            conn.execute(
                insert(acquisition_repair_manifests).values(
                    manifest_id=manifest_id,
                    run_id=str(run_id),
                    preview_fingerprint=run["preview_fingerprint"],
                    fingerprint=frozen_fingerprint,
                    item_count=len(rows),
                    selected_count=selected_count,
                    frozen_by=str(actor),
                    frozen_at=confirmed_at.isoformat(),
                )
            )
            conn.execute(
                update(acquisition_repair_series)
                .where(acquisition_repair_series.c.run_id == str(run_id))
                .values(state="confirmed", updated_at=confirmed_at.isoformat())
            )

            if canary_entity_key is not None:
                entity_type, entity_id = _parse_entity_key(canary_entity_key)
                if canary_entity_key not in selected_keys:
                    raise RepairConfirmationError("canary must be one selected manifest item")
                conn.execute(
                    insert(acquisition_repair_canaries).values(
                        canary_id=str(uuid.uuid4()),
                        run_id=str(run_id),
                        entity_type=entity_type,
                        entity_id=entity_id,
                        owner_id=str(actor),
                        session_digest=run["session_digest"],
                        state="confirmed",
                        confirmed_at=confirmed_at.isoformat(),
                        consumed_at=None,
                    )
                )
            self._event(conn, run_id, "confirm", actor, "repair manifest frozen")

        return {
            "run_id": str(run_id),
            "manifest_id": manifest_id,
            "fingerprint": frozen_fingerprint,
            "item_count": len(rows),
            "selected_count": selected_count,
            "state": "confirmed",
        }

    # ------------------------------------------------------------------
    # Maintenance-fenced CAS apply
    # ------------------------------------------------------------------

    def get_run(self, run_id):
        with self.engine.connect() as conn:
            row = conn.execute(
                select(acquisition_repair_runs).where(acquisition_repair_runs.c.run_id == str(run_id))
            ).first()
        return _row_dict(row)

    def list_items(self, run_id):
        with self.engine.connect() as conn:
            rows = [
                dict(row)
                for row in conn.execute(
                    select(acquisition_repair_items)
                    .where(acquisition_repair_items.c.run_id == str(run_id))
                    .order_by(acquisition_repair_items.c.sequence)
                ).mappings()
            ]
        for row in rows:
            row["evidence"] = _load(row["evidence_json"])
            row["before_values"] = _load(row["before_json"])
            row["proposed_values"] = _load(row["proposed_json"])
            row["entity_key"] = _entity_key(row["entity_type"], row["entity_id"])
        return rows

    def _event(self, conn, run_id, action, actor, reason, item=None):
        conn.execute(
            insert(acquisition_repair_events).values(
                run_id=str(run_id),
                sequence=item.get("sequence") if item else None,
                action=str(action)[:32],
                actor_id=str(actor)[:255],
                entity_type=item.get("entity_type") if item else None,
                entity_id=item.get("entity_id") if item else None,
                reason=_reason(reason),
                created_at=_iso(),
            )
        )

    def _acquire_drained_fence(self, run, actor):
        try:
            fence = self.maintenance.acquire_fence(str(actor), run["run_id"], "acquisition repair apply")
        except MaintenanceConflict as e:
            raise RepairBlocked(str(e)) from e
        with self.engine.begin() as conn:
            conn.execute(
                update(acquisition_repair_runs)
                .where(acquisition_repair_runs.c.run_id == run["run_id"])
                .values(maintenance_epoch=fence.epoch, updated_at=_iso())
            )
        if not fence.drained:
            raise RepairBlocked("active acquisition leases must drain before repair mutation")
        return fence

    def _release_owned_fence(self, run_id, actor):
        status = self.maintenance.status()
        if status.active and status.owner == str(actor) and status.run_id == str(run_id) and status.drained:
            self.maintenance.release_fence(str(actor), str(run_id), status.epoch)

    def _source_predicate(self, table, before):
        predicate = None
        for column in table.columns:
            expected = before.get(column.name)
            comparison = column.is_(None) if expected is None else column == expected
            predicate = comparison if predicate is None else predicate & comparison
        return predicate

    def _after_source_update(self, _conn, _item):
        """Fault-injection seam; production behavior is intentionally empty."""

    def _write_with_retry(self, operation):
        for attempt in range(WRITE_RETRY_LIMIT):
            try:
                return operation()
            except OperationalError as e:
                if attempt + 1 >= WRITE_RETRY_LIMIT or not _is_retryable_write_error(e):
                    raise
                time.sleep(0.05 * (attempt + 1))

    def _apply_item(self, item, actor):
        def operation():
            with self.engine.begin() as conn:
                fresh = (
                    conn.execute(
                        select(acquisition_repair_items).where(acquisition_repair_items.c.item_id == item["item_id"])
                    )
                    .mappings()
                    .one()
                )
                fresh = dict(fresh)
                if fresh["apply_state"] != "pending":
                    return False, fresh["apply_state"]

                table = _SOURCE_TABLES[fresh["entity_type"]]
                id_column = table.c.IssueID
                before = _load(fresh["before_json"])
                proposed = _load(fresh["proposed_json"])
                statement = (
                    update(table)
                    .where(id_column == fresh["entity_id"])
                    .where(self._source_predicate(table, before))
                    .values(**proposed)
                )
                result = conn.execute(statement)
                when = _iso()
                if result.rowcount != 1:
                    conn.execute(
                        update(acquisition_repair_items)
                        .where(acquisition_repair_items.c.item_id == fresh["item_id"])
                        .values(
                            apply_state="conflict",
                            apply_reason="source_changed_since_preview",
                            updated_at=when,
                        )
                    )
                    conn.execute(
                        update(acquisition_repair_series)
                        .where(acquisition_repair_series.c.run_id == fresh["run_id"])
                        .where(acquisition_repair_series.c.series_id == fresh["series_id"])
                        .values(
                            state="conflict",
                            dirty=1,
                            conflict_reason="source_changed_since_preview",
                            updated_at=when,
                        )
                    )
                    conn.execute(
                        update(acquisition_repair_runs)
                        .where(acquisition_repair_runs.c.run_id == fresh["run_id"])
                        .values(
                            conflict_count=acquisition_repair_runs.c.conflict_count + 1,
                            last_sequence=fresh["sequence"],
                            updated_at=when,
                        )
                    )
                    self._event(conn, fresh["run_id"], "conflict", actor, "source changed since preview", fresh)
                    return False, "conflict"

                self._after_source_update(conn, fresh)
                conn.execute(
                    update(acquisition_repair_items)
                    .where(acquisition_repair_items.c.item_id == fresh["item_id"])
                    .values(
                        apply_state="applied",
                        apply_reason=None,
                        applied_json=_json(proposed),
                        applied_at=when,
                        updated_at=when,
                    )
                )
                conn.execute(
                    update(acquisition_repair_series)
                    .where(acquisition_repair_series.c.run_id == fresh["run_id"])
                    .where(acquisition_repair_series.c.series_id == fresh["series_id"])
                    .values(state="dirty", dirty=1, conflict_reason=None, updated_at=when)
                )
                conn.execute(
                    update(acquisition_repair_runs)
                    .where(acquisition_repair_runs.c.run_id == fresh["run_id"])
                    .values(
                        applied_count=acquisition_repair_runs.c.applied_count + 1,
                        last_sequence=fresh["sequence"],
                        updated_at=when,
                    )
                )
                self._event(conn, fresh["run_id"], "apply_item", actor, "compare-and-set applied", fresh)
                return True, "applied"

        return self._write_with_retry(operation)

    def _aggregate_counts(self, conn, series_id):
        issue_total = conn.execute(
            select(func.count()).select_from(issues).where(issues.c.ComicID == str(series_id))
        ).scalar_one()
        annual_filter = (annuals.c.ComicID == str(series_id)) & or_(annuals.c.Deleted.is_(None), annuals.c.Deleted != 1)
        annual_total = conn.execute(select(func.count()).select_from(annuals).where(annual_filter)).scalar_one()
        issue_have = conn.execute(
            select(func.count())
            .select_from(issues)
            .where(issues.c.ComicID == str(series_id), issues.c.Status.in_(tuple(_OWNED_STATUSES)))
        ).scalar_one()
        annual_have = conn.execute(
            select(func.count()).select_from(annuals).where(annual_filter, annuals.c.Status.in_(tuple(_OWNED_STATUSES)))
        ).scalar_one()
        return int(issue_have + annual_have), int(issue_total + annual_total)

    def _finalize_series(self, run_id, actor, *, rollback=False):
        with self.engine.connect() as conn:
            series_rows = [
                dict(row)
                for row in conn.execute(
                    select(acquisition_repair_series).where(acquisition_repair_series.c.run_id == str(run_id))
                ).mappings()
            ]
        conflicts = 0
        for series in series_rows:
            with self.engine.begin() as conn:
                conflict_column = (
                    acquisition_repair_items.c.rollback_state if rollback else acquisition_repair_items.c.apply_state
                )
                conflict_count = conn.execute(
                    select(func.count())
                    .select_from(acquisition_repair_items)
                    .where(
                        acquisition_repair_items.c.run_id == str(run_id),
                        acquisition_repair_items.c.series_id == series["series_id"],
                        conflict_column == "conflict",
                    )
                ).scalar_one()
                if conflict_count:
                    conflicts += int(conflict_count)
                    conn.execute(
                        update(acquisition_repair_series)
                        .where(acquisition_repair_series.c.series_item_id == series["series_item_id"])
                        .values(
                            state="rollback_conflict" if rollback else "conflict",
                            dirty=1,
                            conflict_reason="conditional rollback conflict"
                            if rollback
                            else "source changed since preview",
                            updated_at=_iso(),
                        )
                    )
                    continue
                have, total = self._aggregate_counts(conn, series["series_id"])
                conn.execute(
                    update(comics).where(comics.c.ComicID == series["series_id"]).values(Have=have, Total=total)
                )
                conn.execute(
                    update(acquisition_repair_series)
                    .where(acquisition_repair_series.c.series_item_id == series["series_item_id"])
                    .values(
                        state="rolled_back" if rollback else "finalized",
                        dirty=0,
                        final_have=have,
                        final_total=total,
                        conflict_reason=None,
                        updated_at=_iso(),
                    )
                )
                self._event(conn, run_id, "finalize", actor, "series aggregate finalized")
        return conflicts

    def _result(self, run_id, *, new_mutations=0):
        run = self.get_run(run_id)
        return {
            "run_id": str(run_id),
            "state": run["state"],
            "item_count": run["item_count"],
            "selected_count": run["selected_count"],
            "applied_count": run["applied_count"],
            "conflict_count": run["conflict_count"],
            "rollback_count": run["rollback_count"],
            "rollback_conflict_count": run["rollback_conflict_count"],
            "last_sequence": run["last_sequence"],
            "new_mutations": new_mutations,
        }

    def apply(self, run_id, *, actor, session_id, max_items=None, canary_only=False):
        run = self.get_run(run_id)
        if run is None:
            raise KeyError("unknown repair run")
        self._authorize(run, actor, session_id)
        if run["state"] in {"completed", "needs_review"}:
            self._release_owned_fence(run_id, actor)
            return self._result(run_id, new_mutations=0)
        if run["state"] not in {"confirmed", "applying", "canary_complete"}:
            raise RepairConfirmationError("repair manifest is not confirmed for apply")

        canary = _row_dict(
            self.engine.connect()
            .execute(select(acquisition_repair_canaries).where(acquisition_repair_canaries.c.run_id == str(run_id)))
            .first()
        )
        if canary:
            if canary["owner_id"] != str(actor) or not hmac.compare_digest(
                canary["session_digest"], _digest(session_id)
            ):
                raise RepairConfirmationError("canary is bound to a different owner or session")
            if not canary_only and canary["state"] != "succeeded":
                raise RepairConfirmationError("single-item canary must succeed before full apply")
        elif canary_only:
            raise RepairConfirmationError("this manifest has no confirmed canary")

        fence = self._acquire_drained_fence(run, actor)
        when = _iso()
        with self.engine.begin() as conn:
            conn.execute(
                update(acquisition_repair_runs)
                .where(acquisition_repair_runs.c.run_id == str(run_id))
                .values(
                    state="applying",
                    started_at=run["started_at"] or when,
                    maintenance_epoch=fence.epoch,
                    updated_at=when,
                )
            )
            self._event(conn, run_id, "apply_start", actor, "maintenance fence drained")

        items = self.list_items(run_id)
        selected = [item for item in items if item["selected"]]
        if canary_only:
            selected = [
                item
                for item in selected
                if item["entity_type"] == canary["entity_type"] and item["entity_id"] == canary["entity_id"]
            ]
        processed = 0
        new_mutations = 0
        for item in selected:
            if item["apply_state"] != "pending":
                continue
            if max_items is not None and processed >= int(max_items):
                break
            changed, _state = self._apply_item(item, actor)
            processed += 1
            new_mutations += int(changed)

        if canary_only:
            refreshed = next(
                item
                for item in self.list_items(run_id)
                if item["entity_type"] == canary["entity_type"] and item["entity_id"] == canary["entity_id"]
            )
            canary_state = "succeeded" if refreshed["apply_state"] == "applied" else "conflict"
            with self.engine.begin() as conn:
                conn.execute(
                    update(acquisition_repair_canaries)
                    .where(acquisition_repair_canaries.c.run_id == str(run_id))
                    .values(state=canary_state, consumed_at=_iso())
                )
                conn.execute(
                    update(acquisition_repair_runs)
                    .where(acquisition_repair_runs.c.run_id == str(run_id))
                    .values(
                        state="canary_complete" if canary_state == "succeeded" else "needs_review", updated_at=_iso()
                    )
                )
                self._event(conn, run_id, "canary", actor, "canary %s" % canary_state, refreshed)
            # The fence deliberately remains active between canary and the
            # operator-confirmed full continuation.
            return self._result(run_id, new_mutations=new_mutations)

        remaining = [item for item in self.list_items(run_id) if item["selected"] and item["apply_state"] == "pending"]
        if remaining:
            return self._result(run_id, new_mutations=new_mutations)

        conflicts = self._finalize_series(run_id, actor)
        state = "needs_review" if conflicts else "completed"
        completed = _iso() if not conflicts else None
        with self.engine.begin() as conn:
            conn.execute(
                update(acquisition_repair_runs)
                .where(acquisition_repair_runs.c.run_id == str(run_id))
                .values(state=state, updated_at=_iso(), completed_at=completed)
            )
            self._event(conn, run_id, "apply_complete", actor, state)
        self._release_owned_fence(run_id, actor)
        return self._result(run_id, new_mutations=new_mutations)

    # ------------------------------------------------------------------
    # Conditional rollback
    # ------------------------------------------------------------------

    def _rollback_item(self, item, actor):
        def operation():
            with self.engine.begin() as conn:
                fresh = dict(
                    conn.execute(
                        select(acquisition_repair_items).where(acquisition_repair_items.c.item_id == item["item_id"])
                    )
                    .mappings()
                    .one()
                )
                if fresh["apply_state"] != "applied" or fresh["rollback_state"] != "pending":
                    return False, fresh["rollback_state"]
                table = _SOURCE_TABLES[fresh["entity_type"]]
                proposed = _load(fresh["applied_json"] or fresh["proposed_json"])
                before = _load(fresh["before_json"])
                predicate = table.c.IssueID == fresh["entity_id"]
                restore = {}
                for name, applied in proposed.items():
                    column = table.c[name]
                    predicate = predicate & (column.is_(None) if applied is None else column == applied)
                    restore[name] = before.get(name)
                result = conn.execute(update(table).where(predicate).values(**restore))
                when = _iso()
                if result.rowcount != 1:
                    conn.execute(
                        update(acquisition_repair_items)
                        .where(acquisition_repair_items.c.item_id == fresh["item_id"])
                        .values(
                            rollback_state="conflict",
                            rollback_reason="current_values_differ_from_applied",
                            updated_at=when,
                        )
                    )
                    conn.execute(
                        update(acquisition_repair_runs)
                        .where(acquisition_repair_runs.c.run_id == fresh["run_id"])
                        .values(
                            rollback_conflict_count=acquisition_repair_runs.c.rollback_conflict_count + 1,
                            updated_at=when,
                        )
                    )
                    conn.execute(
                        update(acquisition_repair_series)
                        .where(acquisition_repair_series.c.run_id == fresh["run_id"])
                        .where(acquisition_repair_series.c.series_id == fresh["series_id"])
                        .values(state="rollback_conflict", dirty=1, updated_at=when)
                    )
                    self._event(conn, fresh["run_id"], "rollback_conflict", actor, "applied value drifted", fresh)
                    return False, "conflict"

                conn.execute(
                    update(acquisition_repair_items)
                    .where(acquisition_repair_items.c.item_id == fresh["item_id"])
                    .values(
                        rollback_state="rolled_back",
                        rollback_reason=None,
                        rolled_back_at=when,
                        updated_at=when,
                    )
                )
                conn.execute(
                    update(acquisition_repair_runs)
                    .where(acquisition_repair_runs.c.run_id == fresh["run_id"])
                    .values(
                        rollback_count=acquisition_repair_runs.c.rollback_count + 1,
                        updated_at=when,
                    )
                )
                conn.execute(
                    update(acquisition_repair_series)
                    .where(acquisition_repair_series.c.run_id == fresh["run_id"])
                    .where(acquisition_repair_series.c.series_id == fresh["series_id"])
                    .values(state="rollback_dirty", dirty=1, updated_at=when)
                )
                self._event(conn, fresh["run_id"], "rollback_item", actor, "conditional rollback applied", fresh)
                return True, "rolled_back"

        return self._write_with_retry(operation)

    def rollback(self, run_id, *, actor, session_id, reason):
        if not reason or not str(reason).strip():
            raise ValueError("conditional rollback requires a reason")
        run = self.get_run(run_id)
        if run is None:
            raise KeyError("unknown repair run")
        self._authorize(run, actor, session_id)
        if run["state"] in {"rolled_back", "rollback_needs_review"}:
            return self._result(run_id, new_mutations=0)
        if run["state"] not in {"completed", "needs_review"}:
            raise RepairConfirmationError("repair must finish apply before conditional rollback")

        fence = self._acquire_drained_fence(run, actor)
        with self.engine.begin() as conn:
            conn.execute(
                update(acquisition_repair_runs)
                .where(acquisition_repair_runs.c.run_id == str(run_id))
                .values(state="rolling_back", maintenance_epoch=fence.epoch, updated_at=_iso())
            )
            self._event(conn, run_id, "rollback_start", actor, reason)

        new_mutations = 0
        for item in reversed(self.list_items(run_id)):
            if item["apply_state"] != "applied" or item["rollback_state"] != "pending":
                continue
            changed, _state = self._rollback_item(item, actor)
            new_mutations += int(changed)

        conflicts = self._finalize_series(run_id, actor, rollback=True)
        state = "rollback_needs_review" if conflicts else "rolled_back"
        with self.engine.begin() as conn:
            conn.execute(
                update(acquisition_repair_runs)
                .where(acquisition_repair_runs.c.run_id == str(run_id))
                .values(state=state, updated_at=_iso(), completed_at=_iso())
            )
            self._event(conn, run_id, "rollback_complete", actor, state)
        self._release_owned_fence(run_id, actor)
        return self._result(run_id, new_mutations=new_mutations)

    # ------------------------------------------------------------------
    # Public item projection
    # ------------------------------------------------------------------

    def _public_item(self, item):
        return {
            "sequence": item.get("sequence"),
            "entity_type": item["entity_type"],
            "entity_id": item["entity_id"],
            "entity_key": _entity_key(item["entity_type"], item["entity_id"]),
            "series_id": item["series_id"],
            "intent": item["intent"],
            "fulfillment": item["fulfillment"],
            "reason": item["reason"],
            "date_source": item.get("date_source"),
            "selected_date": item.get("selected_date"),
            "evidence": item["evidence"],
            "proposed_values": item["proposed"],
            "optional": bool(item["optional"]),
            "selected": bool(item["selected"]),
        }
