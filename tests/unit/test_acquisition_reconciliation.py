#  Copyright (C) 2025–2026 Comicarr contributors
#
#  This file is part of Comicarr.
#
#  Comicarr is free software: you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.

"""Evidence-first, immutable acquisition repair contracts."""

import datetime
import json

import pytest
from sqlalchemy import String, inspect, select, update

import comicarr
from comicarr import db
from comicarr.app.acquisition.maintenance import MaintenanceController, ensure_acquisition_schema
from comicarr.app.system.acquisition_repair import (
    RepairBlocked,
    RepairConfirmationError,
    RepairService,
)
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
    metadata,
    pipeline_journal,
)

TODAY = datetime.date(2026, 7, 10)


@pytest.fixture(autouse=True)
def _isolated_db(tmp_path, monkeypatch):
    monkeypatch.setattr(comicarr, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(comicarr, "CONFIG", None, raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("COMICARR_ACQUISITION_MAINTENANCE", raising=False)
    db.shutdown_engine()
    metadata.create_all(db.get_engine())
    assert ensure_acquisition_schema(db.get_engine()).ready
    yield
    db.shutdown_engine()


def _insert_series(tmp_path, comic_id="batman", *, status="Active"):
    library = tmp_path / comic_id
    library.mkdir(parents=True, exist_ok=True)
    with db.get_engine().begin() as conn:
        conn.execute(
            comics.insert().values(
                ComicID=comic_id,
                ComicName="Absolute Batman",
                ComicYear="2024",
                ComicLocation=str(library),
                Status=status,
                Have=999,
                Total=999,
            )
        )
    return library


def _insert_issue(issue_id, number, *, comic_id="batman", status=None, intent=None, location=None, date="2026-01-01"):
    with db.get_engine().begin() as conn:
        conn.execute(
            issues.insert().values(
                IssueID=str(issue_id),
                ComicID=comic_id,
                ComicName="Absolute Batman",
                Issue_Number=str(number),
                Int_IssueNumber=int(number),
                Status=status,
                AcquisitionIntent=intent,
                Location=location,
                ReleaseDate=date,
                DigitalDate=None,
                IssueDate=date,
            )
        )


def _insert_annual(
    issue_id,
    number,
    *,
    comic_id="batman",
    status=None,
    intent=None,
    location=None,
    date="2026-01-01",
    deleted=None,
):
    with db.get_engine().begin() as conn:
        conn.execute(
            annuals.insert().values(
                IssueID=str(issue_id),
                ComicID=comic_id,
                ComicName="Absolute Batman Annual",
                Issue_Number=str(number),
                Int_IssueNumber=int(number),
                Status=status,
                AcquisitionIntent=intent,
                Location=location,
                ReleaseDate=date,
                DigitalDate=None,
                IssueDate=date,
                Deleted=deleted,
            )
        )


def _row(table, predicate):
    with db.get_engine().connect() as conn:
        result = conn.execute(select(table).where(predicate)).first()
    return dict(result._mapping) if result else None


def _absolute_batman_fixture(tmp_path):
    library = _insert_series(tmp_path)
    for number in range(1, 19):
        filename = "Absolute Batman %03d.cbz" % number
        (library / filename).write_bytes(b"comic")
        _insert_issue("owned-%02d" % number, number, status="Skipped", location=filename)
    _insert_issue("released-19", 19, status="Skipped", date="2026-06-01")
    _insert_issue("released-20", 20, status="Skipped", date="2026-07-01")
    _insert_issue("future-21", 21, status="Skipped", date="2026-08-01")
    _insert_issue("future-22", 22, status="Skipped", date="2026-09-01")


def _preview(service, *, selected_session="session-owner"):
    return service.preview_series(
        "batman",
        actor="owner",
        session_id=selected_session,
        today=TODAY,
    )


def _confirm(service, preview, *, selected=(), session_id="session-owner", canary=None):
    return service.confirm(
        preview["run_id"],
        preview_token=preview["preview_token"],
        fingerprint=preview["fingerprint"],
        actor="owner",
        session_id=session_id,
        selected_optional_keys=selected,
        canary_entity_key=canary,
    )


def test_schema_v2_declares_all_repair_tables_and_bounded_indexed_identifiers():
    table_names = set(inspect(db.get_engine()).get_table_names())
    expected = {
        "acquisition_repair_runs",
        "acquisition_repair_manifests",
        "acquisition_repair_items",
        "acquisition_repair_series",
        "acquisition_repair_events",
        "acquisition_repair_canaries",
    }
    assert expected <= table_names

    indexed_columns = {
        acquisition_repair_runs.c.run_id,
        acquisition_repair_runs.c.state,
        acquisition_repair_manifests.c.manifest_id,
        acquisition_repair_manifests.c.run_id,
        acquisition_repair_items.c.run_id,
        acquisition_repair_items.c.entity_type,
        acquisition_repair_items.c.entity_id,
        acquisition_repair_items.c.apply_state,
        acquisition_repair_series.c.run_id,
        acquisition_repair_series.c.series_id,
        acquisition_repair_events.c.run_id,
        acquisition_repair_canaries.c.run_id,
        acquisition_repair_canaries.c.entity_id,
    }
    assert all(isinstance(column.type, String) and column.type.length for column in indexed_columns)


def test_absolute_batman_preview_is_read_only_and_conservative(tmp_path):
    _absolute_batman_fixture(tmp_path)
    before = _row(comics, comics.c.ComicID == "batman")

    preview = _preview(RepairService(db.get_engine()))

    assert preview["summary"] == {
        "total": 22,
        "owned": 18,
        "archived": 0,
        "in_flight": 0,
        "failed": 0,
        "optional_wanted": 2,
        "future": 2,
        "unknown": 0,
        "selected": 18,
    }
    assert _row(comics, comics.c.ComicID == "batman") == before
    with db.get_engine().connect() as conn:
        source_statuses = list(conn.execute(select(issues.c.Status).order_by(issues.c.Int_IssueNumber)).scalars())
        stored_run = (
            conn.execute(select(acquisition_repair_runs).where(acquisition_repair_runs.c.run_id == preview["run_id"]))
            .mappings()
            .one()
        )
    assert source_statuses == ["Skipped"] * 22
    assert preview["preview_token"] not in json.dumps(dict(stored_run), default=str)
    optional = [item for item in preview["items"] if item["optional"]]
    assert [item["entity_key"] for item in optional] == ["issue:released-19", "issue:released-20"]


def test_confirmation_is_session_bound_single_use_and_freezes_selection(tmp_path):
    _absolute_batman_fixture(tmp_path)
    service = RepairService(db.get_engine())
    preview = _preview(service)

    with pytest.raises(RepairConfirmationError, match="session"):
        _confirm(service, preview, session_id="different-session")

    confirmed = _confirm(service, preview, selected=("issue:released-19",))
    assert confirmed["selected_count"] == 19
    assert confirmed["item_count"] == 22

    with pytest.raises(RepairConfirmationError, match="consumed|confirmed"):
        _confirm(service, preview, selected=("issue:released-20",))

    with db.get_engine().connect() as conn:
        manifest = (
            conn.execute(
                select(acquisition_repair_manifests).where(acquisition_repair_manifests.c.run_id == preview["run_id"])
            )
            .mappings()
            .one()
        )
        rows = list(
            conn.execute(
                select(acquisition_repair_items)
                .where(acquisition_repair_items.c.run_id == preview["run_id"])
                .order_by(acquisition_repair_items.c.sequence)
            ).mappings()
        )
    assert manifest["fingerprint"] == confirmed["fingerprint"]
    assert [row["sequence"] for row in rows] == list(range(1, 23))
    selected = {"%s:%s" % (row["entity_type"], row["entity_id"]) for row in rows if row["selected"]}
    assert "issue:released-19" in selected
    assert "issue:released-20" not in selected


def test_expired_confirmation_token_does_not_freeze_manifest(tmp_path):
    _insert_series(tmp_path)
    _insert_issue("one", 1)
    service = RepairService(db.get_engine())
    preview = service.preview_series(
        "batman",
        actor="owner",
        session_id="session-owner",
        today=TODAY,
        now=datetime.datetime(2026, 7, 10, tzinfo=datetime.timezone.utc),
        token_ttl_seconds=1,
    )

    with pytest.raises(RepairConfirmationError, match="expired"):
        service.confirm(
            preview["run_id"],
            preview_token=preview["preview_token"],
            fingerprint=preview["fingerprint"],
            actor="owner",
            session_id="session-owner",
            now=datetime.datetime(2026, 7, 10, 0, 0, 2, tzinfo=datetime.timezone.utc),
        )
    assert _row(acquisition_repair_manifests, acquisition_repair_manifests.c.run_id == preview["run_id"]) is None


def test_apply_requires_drained_fence_then_uses_null_safe_cas(tmp_path):
    _insert_series(tmp_path)
    _insert_issue("one", 1, date="2026-01-01")
    service = RepairService(db.get_engine())
    preview = _preview(service)
    _confirm(service, preview, selected=("issue:one",))

    controller = MaintenanceController(db.get_engine())
    lease = controller.acquire_lease("worker", "postprocess", "issue", "other")
    with pytest.raises(RepairBlocked, match="lease"):
        service.apply(preview["run_id"], actor="owner", session_id="session-owner")
    assert _row(issues, issues.c.IssueID == "one")["Status"] is None

    controller.release_lease(lease.lease_id)
    result = service.apply(preview["run_id"], actor="owner", session_id="session-owner")
    assert result["state"] == "completed"
    assert result["applied_count"] == 1
    assert _row(issues, issues.c.IssueID == "one")["Status"] == "Wanted"
    assert _row(comics, comics.c.ComicID == "batman")["Have"] == 0
    assert _row(comics, comics.c.ComicID == "batman")["Total"] == 1
    assert MaintenanceController(db.get_engine()).status().active is False


def test_complete_before_value_cas_reports_concurrent_null_drift(tmp_path):
    _insert_series(tmp_path)
    _insert_issue("one", 1, date="2026-01-01")
    service = RepairService(db.get_engine())
    preview = _preview(service)
    _confirm(service, preview, selected=("issue:one",))

    with db.get_engine().begin() as conn:
        conn.execute(update(issues).where(issues.c.IssueID == "one").values(IssueName="changed after preview"))

    result = service.apply(preview["run_id"], actor="owner", session_id="session-owner")

    assert result["state"] == "needs_review"
    assert result["conflict_count"] == 1
    assert _row(issues, issues.c.IssueID == "one")["Status"] is None
    item = service.list_items(preview["run_id"])[0]
    assert item["apply_state"] == "conflict"
    assert item["apply_reason"] == "source_changed_since_preview"
    series = _row(
        acquisition_repair_series,
        (acquisition_repair_series.c.run_id == preview["run_id"]) & (acquisition_repair_series.c.series_id == "batman"),
    )
    assert series["dirty"] == 1


def test_item_transaction_rolls_back_source_manifest_dirty_and_checkpoint_then_resumes(tmp_path, monkeypatch):
    _insert_series(tmp_path)
    _insert_issue("one", 1, date="2026-01-01")
    service = RepairService(db.get_engine())
    preview = _preview(service)
    _confirm(service, preview, selected=("issue:one",))

    def fail_after_source(*_args):
        raise RuntimeError("crash after source update")

    monkeypatch.setattr(service, "_after_source_update", fail_after_source)
    with pytest.raises(RuntimeError, match="crash after source"):
        service.apply(preview["run_id"], actor="owner", session_id="session-owner")

    assert _row(issues, issues.c.IssueID == "one")["Status"] is None
    assert service.list_items(preview["run_id"])[0]["apply_state"] == "pending"
    assert service.get_run(preview["run_id"])["last_sequence"] == 0
    assert (
        _row(
            acquisition_repair_series,
            acquisition_repair_series.c.run_id == preview["run_id"],
        )["dirty"]
        == 0
    )

    monkeypatch.setattr(service, "_after_source_update", lambda *_args: None)
    first = service.apply(preview["run_id"], actor="owner", session_id="session-owner")
    second = service.apply(preview["run_id"], actor="owner", session_id="session-owner")
    assert first["applied_count"] == 1
    assert second["applied_count"] == 1
    assert second["new_mutations"] == 0


def test_precedence_preserves_explicit_intent_beside_owned_and_inflight(tmp_path):
    library = _insert_series(tmp_path)
    (library / "owned.cbz").write_bytes(b"owned")
    _insert_issue("owned-skip", 1, status="Skipped", intent="skipped", location="owned.cbz")
    _insert_issue("inflight-ignore", 2, status=None, intent="ignored")
    _insert_issue("legacy-skip", 3, status="Skipped", intent=None)
    _insert_issue("failed-ddl", 4, status=None, intent=None)
    _insert_issue("ambiguous-ddl", 5, status=None, intent=None)
    with db.get_engine().begin() as conn:
        conn.execute(
            pipeline_journal.insert().values(
                release_key="inflight-ignore|provider",
                issueid="inflight-ignore",
                provider="provider",
                downloader_type="sab",
                stage="snatched",
                stage_rank=10,
                updated_date="2026-07-10 00:00:00",
            )
        )
        conn.execute(ddl_info.insert().values(ID="failed", issueid="failed-ddl", comicid="batman", status="Failed"))
        conn.execute(
            ddl_info.insert().values(ID="ambiguous", issueid="ambiguous-ddl", comicid="batman", status="Downloading")
        )

    preview = _preview(RepairService(db.get_engine()))
    items = {item["entity_key"]: item for item in preview["items"]}

    assert items["issue:owned-skip"]["fulfillment"] == "downloaded"
    assert items["issue:owned-skip"]["intent"] == "skipped"
    assert items["issue:owned-skip"]["proposed_values"] == {"Status": "Downloaded"}
    assert items["issue:inflight-ignore"]["fulfillment"] == "snatched"
    assert items["issue:inflight-ignore"]["intent"] == "ignored"
    assert items["issue:legacy-skip"]["intent"] == "policy"
    assert items["issue:legacy-skip"]["fulfillment"] == "missing"
    assert items["issue:legacy-skip"]["optional"] is True
    assert items["issue:legacy-skip"]["proposed_values"] == {"Status": "Wanted"}
    assert items["issue:failed-ddl"]["fulfillment"] == "failed"
    assert items["issue:ambiguous-ddl"]["fulfillment"] == "unknown"
    assert items["issue:ambiguous-ddl"]["reason"] == "legacy_ddl_downloading_unproven"


def test_archived_reserved_and_null_deleted_annual_participate_in_preview_and_aggregate(tmp_path):
    library = _insert_series(tmp_path)
    annual_name = "Absolute Batman Annual 001.cbz"
    (library / annual_name).write_bytes(b"annual")
    _insert_issue("archived", 1, status="Archived", date="2025-01-01")
    _insert_issue("reserved", 2, status="Skipped", date="2025-02-01")
    _insert_annual(
        "annual-owned",
        1,
        status="Skipped",
        location=annual_name,
        date="2025-03-01",
        deleted=None,
    )
    with db.get_engine().begin() as conn:
        conn.execute(
            pipeline_journal.insert().values(
                release_key="reserved|provider",
                issueid="reserved",
                provider="provider",
                downloader_type="sab",
                stage="reserved",
                stage_rank=5,
                updated_date="2026-07-10 00:00:00",
            )
        )

    service = RepairService(db.get_engine())
    preview = _preview(service)
    items = {item["entity_key"]: item for item in preview["items"]}
    assert items["issue:archived"]["fulfillment"] == "archived"
    assert items["issue:reserved"]["fulfillment"] == "reserved"
    assert items["annual:annual-owned"]["fulfillment"] == "downloaded"
    assert preview["summary"]["owned"] == 2
    assert preview["summary"]["archived"] == 1
    assert preview["summary"]["in_flight"] == 1

    _confirm(service, preview)
    result = service.apply(preview["run_id"], actor="owner", session_id="session-owner")
    assert result["state"] == "completed"
    series = _row(comics, comics.c.ComicID == "batman")
    assert series["Have"] == 2
    assert series["Total"] == 3


def test_canary_is_bound_to_owner_session_and_single_manifest_item(tmp_path):
    _insert_series(tmp_path)
    _insert_issue("one", 1)
    _insert_issue("two", 2)
    service = RepairService(db.get_engine())
    preview = _preview(service)
    _confirm(
        service,
        preview,
        selected=("issue:one", "issue:two"),
        canary="issue:one",
    )

    with pytest.raises(RepairConfirmationError, match="session"):
        service.apply(
            preview["run_id"],
            actor="owner",
            session_id="different-session",
            canary_only=True,
        )

    canary = service.apply(
        preview["run_id"],
        actor="owner",
        session_id="session-owner",
        canary_only=True,
    )
    assert canary["state"] == "canary_complete"
    assert _row(issues, issues.c.IssueID == "one")["Status"] == "Wanted"
    assert _row(issues, issues.c.IssueID == "two")["Status"] is None
    stored = _row(acquisition_repair_canaries, acquisition_repair_canaries.c.run_id == preview["run_id"])
    assert stored["entity_id"] == "one"
    assert stored["state"] == "succeeded"

    completed = service.apply(preview["run_id"], actor="owner", session_id="session-owner")
    assert completed["state"] == "completed"
    assert _row(issues, issues.c.IssueID == "two")["Status"] == "Wanted"


def test_conditional_rollback_restores_only_unchanged_applied_values(tmp_path):
    _insert_series(tmp_path)
    _insert_issue("one", 1)
    _insert_issue("two", 2)
    service = RepairService(db.get_engine())
    preview = _preview(service)
    _confirm(service, preview, selected=("issue:one", "issue:two"))
    service.apply(preview["run_id"], actor="owner", session_id="session-owner")

    with db.get_engine().begin() as conn:
        conn.execute(update(issues).where(issues.c.IssueID == "two").values(Status="Skipped"))

    rolled = service.rollback(
        preview["run_id"],
        actor="owner",
        session_id="session-owner",
        reason="operator requested conditional rollback",
    )

    assert rolled["state"] == "rollback_needs_review"
    assert _row(issues, issues.c.IssueID == "one")["Status"] is None
    assert _row(issues, issues.c.IssueID == "two")["Status"] == "Skipped"
    items = {item["entity_id"]: item for item in service.list_items(preview["run_id"])}
    assert items["one"]["rollback_state"] == "rolled_back"
    assert items["two"]["rollback_state"] == "conflict"


def test_audit_events_do_not_store_preview_token(tmp_path):
    _insert_series(tmp_path)
    _insert_issue("one", 1)
    service = RepairService(db.get_engine())
    preview = _preview(service)
    _confirm(service, preview, selected=("issue:one",))

    with db.get_engine().connect() as conn:
        events = [dict(row._mapping) for row in conn.execute(select(acquisition_repair_events))]
    assert events
    assert preview["preview_token"] not in json.dumps(events, default=str)
