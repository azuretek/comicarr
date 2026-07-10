#  Copyright (C) 2025–2026 Comicarr contributors
#
#  This file is part of Comicarr.
#
#  Comicarr is free software: you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.

"""SQLAlchemy Core persistence for generic acquisition commands and items."""

import datetime
import json

from sqlalchemy import func, insert, select, update
from sqlalchemy.exc import IntegrityError

from comicarr.app.acquisition.models import DispatchState, ItemOutcome, RunState
from comicarr.db import get_engine
from comicarr.tables import acquisition_run_items, acquisition_runs

MAX_PAYLOAD_BYTES = 16 * 1024
PAYLOAD_FIELDS = {
    "search": frozenset(
        {
            "comicid",
            "issueid",
            "comicname",
            "issue_number",
            "seriesyear",
            "mode",
            "manual",
            "annual",
            "storyarc",
        }
    ),
    "refresh": frozenset(
        {
            "comicid",
            "comicname",
            "seriesyear",
            "r_mode",
            "calledfrom",
            "serieslast_updated",
            "manual_comicid",
        }
    ),
}


def _utcnow():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def _value(value):
    return value.value if hasattr(value, "value") else str(value)


def _row_dict(row):
    return dict(row._mapping) if row is not None else None


def _payload_json(command_kind, payload):
    if payload is None:
        return None
    if not isinstance(payload, dict):
        raise ValueError("acquisition payload must be a dictionary")
    allowed = PAYLOAD_FIELDS.get(command_kind)
    if allowed is None:
        raise ValueError("payloads are not enabled for command kind %s" % command_kind)
    unexpected = sorted(set(payload) - allowed)
    if unexpected:
        raise ValueError("payload contains non-allowlisted fields: %s" % ", ".join(unexpected))
    try:
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    except (TypeError, ValueError) as e:
        raise ValueError("acquisition payload must be JSON serializable") from e
    if len(encoded.encode("utf-8")) > MAX_PAYLOAD_BYTES:
        raise ValueError("acquisition payload exceeds %s bytes" % MAX_PAYLOAD_BYTES)
    return encoded


def _decode_payload(encoded):
    return json.loads(encoded) if encoded else None


class RunLedger:
    """Durable run/item owner shared by refresh, search, and later adapters."""

    def __init__(self, engine=None):
        self.engine = engine or get_engine()

    def create_run(self, run_id, command_kind, trigger, scope_type=None, scope_id=None):
        command_kind = str(command_kind).strip().lower()
        if not run_id or not command_kind or not trigger:
            raise ValueError("run_id, command_kind, and trigger are required")
        now = _utcnow()
        values = {
            "run_id": str(run_id),
            "command_kind": command_kind,
            "trigger": str(trigger),
            "scope_type": str(scope_type) if scope_type is not None else None,
            "scope_id": str(scope_id) if scope_id is not None else None,
            "dispatch_state": DispatchState.PENDING.value,
            "completion_state": RunState.PENDING.value,
            "accepted_count": 0,
            "terminal_count": 0,
            "succeeded_count": 0,
            "no_match_count": 0,
            "blocked_count": 0,
            "failed_count": 0,
            "created_at": now,
            "updated_at": now,
            "completed_at": None,
        }
        try:
            with self.engine.begin() as conn:
                conn.execute(insert(acquisition_runs).values(**values))
        except IntegrityError:
            existing = self.get_run(run_id)
            immutable = ("command_kind", "trigger", "scope_type", "scope_id")
            if existing is None or any(existing[key] != values[key] for key in immutable):
                raise ValueError("run_id already belongs to a different acquisition command")
        return self.get_run(run_id)

    def get_run(self, run_id):
        with self.engine.connect() as conn:
            row = conn.execute(select(acquisition_runs).where(acquisition_runs.c.run_id == str(run_id))).first()
        return _row_dict(row)

    def _require_run(self, run_id):
        run = self.get_run(run_id)
        if run is None:
            raise KeyError("unknown acquisition run %s" % run_id)
        return run

    def accept_item(self, run_id, entity_type, entity_id, payload=None, command_kind=None):
        run = self._require_run(run_id)
        effective_kind = str(command_kind or run["command_kind"]).strip().lower()
        if effective_kind != run["command_kind"]:
            raise ValueError("item command_kind must match its acquisition run")
        encoded = _payload_json(effective_kind, payload)
        now = _utcnow()
        values = {
            "run_id": str(run_id),
            "command_kind": effective_kind,
            "entity_type": str(entity_type),
            "entity_id": str(entity_id),
            "state": ItemOutcome.ACCEPTED.value,
            "payload_json": encoded,
            "attempt_count": 0,
            "next_attempt_at": None,
            "reason": None,
            "created_at": now,
            "updated_at": now,
            "completed_at": None,
        }
        try:
            with self.engine.begin() as conn:
                conn.execute(insert(acquisition_run_items).values(**values))
        except IntegrityError:
            existing = self.get_item(run_id, entity_type, entity_id)
            if existing is None:
                raise
            if encoded is not None and existing["payload_json"] not in (None, encoded):
                raise ValueError("accepted acquisition item payload is immutable")
            if existing["payload_json"] is None and encoded is not None:
                with self.engine.begin() as conn:
                    conn.execute(
                        update(acquisition_run_items)
                        .where(acquisition_run_items.c.item_id == existing["item_id"])
                        .where(
                            acquisition_run_items.c.state.in_([ItemOutcome.ACCEPTED.value, ItemOutcome.RUNNING.value])
                        )
                        .values(payload_json=encoded, updated_at=now)
                    )
        self.reconcile(run_id)
        return self.get_item(run_id, entity_type, entity_id)

    def get_item(self, run_id, entity_type, entity_id):
        run = self._require_run(run_id)
        stmt = select(acquisition_run_items).where(
            acquisition_run_items.c.run_id == str(run_id),
            acquisition_run_items.c.command_kind == run["command_kind"],
            acquisition_run_items.c.entity_type == str(entity_type),
            acquisition_run_items.c.entity_id == str(entity_id),
        )
        with self.engine.connect() as conn:
            row = conn.execute(stmt).first()
        return _row_dict(row)

    def record_dispatch(self, run_id, state):
        self._require_run(run_id)
        state = DispatchState(_value(state))
        with self.engine.begin() as conn:
            conn.execute(
                update(acquisition_runs)
                .where(acquisition_runs.c.run_id == str(run_id))
                .values(dispatch_state=state.value, updated_at=_utcnow())
            )
        return self.get_run(run_id)

    def claim_item(self, run_id, entity_type, entity_id):
        item = self.get_item(run_id, entity_type, entity_id)
        if item is None:
            raise KeyError("unknown acquisition item")
        if item["state"] != ItemOutcome.ACCEPTED.value:
            return False
        now = _utcnow()
        with self.engine.begin() as conn:
            result = conn.execute(
                update(acquisition_run_items)
                .where(acquisition_run_items.c.item_id == item["item_id"])
                .where(acquisition_run_items.c.state == ItemOutcome.ACCEPTED.value)
                .values(
                    state=ItemOutcome.RUNNING.value,
                    attempt_count=acquisition_run_items.c.attempt_count + 1,
                    next_attempt_at=None,
                    updated_at=now,
                )
            )
        return result.rowcount == 1

    def record_requeue(self, run_id, entity_type, entity_id, reason, next_attempt_at=None):
        item = self.get_item(run_id, entity_type, entity_id)
        if item is None:
            raise KeyError("unknown acquisition item")
        current = ItemOutcome(item["state"])
        if current.terminal:
            raise ValueError("terminal acquisition items cannot be requeued implicitly")
        with self.engine.begin() as conn:
            conn.execute(
                update(acquisition_run_items)
                .where(acquisition_run_items.c.item_id == item["item_id"])
                .values(
                    state=ItemOutcome.ACCEPTED.value,
                    reason=str(reason)[:1000] if reason else None,
                    next_attempt_at=next_attempt_at,
                    updated_at=_utcnow(),
                )
            )
        self.reconcile(run_id)
        return self.get_item(run_id, entity_type, entity_id)

    def record_outcome(self, run_id, entity_type, entity_id, outcome, reason=None):
        item = self.get_item(run_id, entity_type, entity_id)
        if item is None:
            raise KeyError("unknown acquisition item")
        outcome = ItemOutcome(_value(outcome))
        if not outcome.terminal:
            raise ValueError("record_outcome requires a terminal item outcome")
        current = ItemOutcome(item["state"])
        if current.terminal and current is not outcome:
            raise ValueError("terminal acquisition outcome cannot be replaced")
        if current is not outcome:
            now = _utcnow()
            with self.engine.begin() as conn:
                conn.execute(
                    update(acquisition_run_items)
                    .where(acquisition_run_items.c.item_id == item["item_id"])
                    .where(acquisition_run_items.c.state.in_([ItemOutcome.ACCEPTED.value, ItemOutcome.RUNNING.value]))
                    .values(
                        state=outcome.value,
                        reason=str(reason)[:1000] if reason else None,
                        next_attempt_at=None,
                        updated_at=now,
                        completed_at=now,
                    )
                )
        return self.reconcile(run_id)

    def list_recoverable_items(self, command_kind=None):
        stmt = (
            select(acquisition_run_items)
            .where(acquisition_run_items.c.state.in_([ItemOutcome.ACCEPTED.value, ItemOutcome.RUNNING.value]))
            .order_by(acquisition_run_items.c.item_id)
        )
        if command_kind is not None:
            stmt = stmt.where(acquisition_run_items.c.command_kind == str(command_kind).strip().lower())
        with self.engine.connect() as conn:
            rows = [dict(row._mapping) for row in conn.execute(stmt)]
        for row in rows:
            row["payload"] = _decode_payload(row["payload_json"])
        return rows

    def reconcile(self, run_id):
        self._require_run(run_id)
        with self.engine.begin() as conn:
            counts = dict(
                tuple(row)
                for row in conn.execute(
                    select(acquisition_run_items.c.state, func.count())
                    .where(acquisition_run_items.c.run_id == str(run_id))
                    .group_by(acquisition_run_items.c.state)
                )
            )
            accepted_count = sum(counts.values())
            terminal_count = sum(count for state, count in counts.items() if ItemOutcome(state).terminal)
            succeeded = counts.get(ItemOutcome.SUCCEEDED.value, 0)
            no_match = counts.get(ItemOutcome.NO_MATCH.value, 0)
            blocked = counts.get(ItemOutcome.BLOCKED.value, 0)
            failed = sum(
                counts.get(state.value, 0)
                for state in (ItemOutcome.FAILED, ItemOutcome.QUARANTINED, ItemOutcome.CANCELLED)
            )

            if accepted_count == 0:
                completion = RunState.PENDING
            elif terminal_count < accepted_count:
                completion = RunState.RUNNING
            elif failed == accepted_count:
                completion = RunState.FAILED
            elif blocked == accepted_count:
                completion = RunState.BLOCKED
            elif failed or blocked:
                completion = RunState.PARTIAL
            else:
                completion = RunState.COMPLETED
            now = _utcnow()
            completed_at = now if terminal_count == accepted_count and accepted_count else None
            conn.execute(
                update(acquisition_runs)
                .where(acquisition_runs.c.run_id == str(run_id))
                .values(
                    completion_state=completion.value,
                    accepted_count=accepted_count,
                    terminal_count=terminal_count,
                    succeeded_count=succeeded,
                    no_match_count=no_match,
                    blocked_count=blocked,
                    failed_count=failed,
                    updated_at=now,
                    completed_at=completed_at,
                )
            )
        return self.get_run(run_id)
