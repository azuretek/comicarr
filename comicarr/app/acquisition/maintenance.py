#  Copyright (C) 2025–2026 Comicarr contributors
#
#  This file is part of Comicarr.
#
#  Comicarr is free software: you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.

"""Versioned acquisition schema and persistent maintenance fencing."""

import datetime
import os
import uuid
from contextlib import contextmanager
from dataclasses import dataclass

from sqlalchemy import func, insert, inspect, literal, select, text, update
from sqlalchemy.exc import IntegrityError

import comicarr
from comicarr.db import get_engine
from comicarr.tables import (
    acquisition_maintenance,
    acquisition_maintenance_events,
    acquisition_maintenance_leases,
    acquisition_run_items,
    acquisition_runs,
    acquisition_schema_versions,
    annuals,
    issues,
)

SCHEMA_COMPONENT = "acquisition"
SCHEMA_VERSION = 1
CONTROL_ID = "acquisition"

_SCHEMA_TABLES = (
    acquisition_schema_versions,
    acquisition_runs,
    acquisition_run_items,
    acquisition_maintenance,
    acquisition_maintenance_leases,
    acquisition_maintenance_events,
)
_REQUIRED_INDEXES = {
    "issues": {"issues_acquisition_intent"},
    "annuals": {"annuals_acquisition_intent"},
    "acquisition_runs": {"acquisition_runs_state"},
    "acquisition_run_items": {"acquisition_run_items_run_state", "acquisition_run_items_entity"},
    "acquisition_maintenance_leases": {"acquisition_maintenance_leases_active"},
    "acquisition_maintenance_events": {"acquisition_maintenance_events_epoch"},
}


def _utcnow():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def _truthy(value):
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class SchemaStatus:
    ready: bool
    version: int
    error: str | None = None


@dataclass(frozen=True)
class FenceStatus:
    active: bool
    epoch: int
    owner: str | None
    run_id: str | None
    reason: str | None
    heartbeat_at: str | None
    active_leases: int

    @property
    def drained(self):
        return self.active_leases == 0


@dataclass(frozen=True)
class Lease:
    lease_id: str
    epoch: int
    owner: str
    work_kind: str
    entity_type: str | None = None
    entity_id: str | None = None


@dataclass(frozen=True)
class RuntimeGateStatus:
    blocked: bool
    reason: str | None
    schema_ready: bool
    maintenance_active: bool
    epoch: int
    owner: str | None = None
    run_id: str | None = None
    heartbeat_at: str | None = None

    def as_dict(self):
        return {
            "blocked": self.blocked,
            "reason": self.reason,
            "schema_ready": self.schema_ready,
            "maintenance_active": self.maintenance_active,
            "epoch": self.epoch,
            "owner": self.owner,
            "run_id": self.run_id,
            "heartbeat_at": self.heartbeat_at,
        }


class MaintenanceBlocked(RuntimeError):
    """A maintenance fence or startup gate rejected new acquisition work."""


class MaintenanceConflict(RuntimeError):
    """A different owner or active lease prevents a fence transition."""


def _set_schema_globals(status):
    comicarr.ACQUISITION_SCHEMA_READY = status.ready
    comicarr.ACQUISITION_SCHEMA_VERSION = status.version
    comicarr.ACQUISITION_SCHEMA_ERROR = status.error


def _current_version(engine):
    with engine.connect() as conn:
        value = conn.execute(
            select(func.max(acquisition_schema_versions.c.version)).where(
                acquisition_schema_versions.c.component == SCHEMA_COMPONENT
            )
        ).scalar_one_or_none()
    return int(value or 0)


def _create_declared_index(engine, table, index_name):
    index = next((candidate for candidate in table.indexes if candidate.name == index_name), None)
    if index is None:
        raise RuntimeError("missing declared acquisition index %s" % index_name)
    index.create(engine, checkfirst=True)


def _add_intent_column(engine, table_name):
    inspector = inspect(engine)
    columns = {column["name"] for column in inspector.get_columns(table_name)}
    if "AcquisitionIntent" in columns:
        return
    quoted_table = engine.dialect.identifier_preparer.quote(table_name)
    quoted_column = engine.dialect.identifier_preparer.quote("AcquisitionIntent")
    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE %s ADD COLUMN %s TEXT" % (quoted_table, quoted_column)))


def _ensure_control_row(engine):
    try:
        with engine.begin() as conn:
            conn.execute(
                insert(acquisition_maintenance).values(
                    control_id=CONTROL_ID,
                    epoch=0,
                    active=0,
                    owner=None,
                    run_id=None,
                    reason=None,
                    acquired_at=None,
                    heartbeat_at=None,
                    released_at=None,
                )
            )
    except IntegrityError:
        pass


def _apply_schema_v1(engine):
    for table in _SCHEMA_TABLES:
        table.create(engine, checkfirst=True)
    _add_intent_column(engine, "issues")
    _add_intent_column(engine, "annuals")
    _create_declared_index(engine, issues, "issues_acquisition_intent")
    _create_declared_index(engine, annuals, "annuals_acquisition_intent")
    for table_name, names in _REQUIRED_INDEXES.items():
        if table_name in {"issues", "annuals"}:
            continue
        table = next(table for table in _SCHEMA_TABLES if table.name == table_name)
        for name in names:
            _create_declared_index(engine, table, name)
    _ensure_control_row(engine)


def _verify_schema(engine):
    inspector = inspect(engine)
    actual_tables = set(inspector.get_table_names())
    required_tables = {"issues", "annuals"} | {table.name for table in _SCHEMA_TABLES}
    missing_tables = sorted(required_tables - actual_tables)
    if missing_tables:
        raise RuntimeError("missing acquisition tables: %s" % ", ".join(missing_tables))

    required_columns = {
        "issues": {"AcquisitionIntent"},
        "annuals": {"AcquisitionIntent"},
        **{table.name: {column.name for column in table.columns} for table in _SCHEMA_TABLES},
    }
    missing_columns = []
    for table_name, expected in required_columns.items():
        actual = {column["name"] for column in inspector.get_columns(table_name)}
        missing_columns.extend("%s.%s" % (table_name, name) for name in sorted(expected - actual))
    if missing_columns:
        raise RuntimeError("missing acquisition columns: %s" % ", ".join(missing_columns))

    missing_indexes = []
    for table_name, expected in _REQUIRED_INDEXES.items():
        actual = {index["name"] for index in inspector.get_indexes(table_name)}
        missing_indexes.extend(sorted(expected - actual))
    if missing_indexes:
        raise RuntimeError("missing acquisition indexes: %s" % ", ".join(missing_indexes))

    with engine.connect() as conn:
        control = conn.execute(
            select(acquisition_maintenance.c.control_id).where(acquisition_maintenance.c.control_id == CONTROL_ID)
        ).first()
    if control is None:
        raise RuntimeError("missing acquisition maintenance control row")


def ensure_acquisition_schema(engine=None):
    """Apply forward-only acquisition schema versions, then verify exactly.

    Errors are returned as a fail-closed status rather than raised so the web
    process can still expose authenticated diagnostics. Callers must honor the
    resulting runtime gate before starting or claiming acquisition work.
    """

    engine = engine or get_engine()
    version = 0
    try:
        acquisition_schema_versions.create(engine, checkfirst=True)
        version = _current_version(engine)
        if version > SCHEMA_VERSION:
            raise RuntimeError(
                "database acquisition schema version %s is newer than supported version %s" % (version, SCHEMA_VERSION)
            )
        if version < 1:
            _apply_schema_v1(engine)
            _verify_schema(engine)
            with engine.begin() as conn:
                conn.execute(
                    insert(acquisition_schema_versions).values(
                        component=SCHEMA_COMPONENT,
                        version=1,
                        applied_at=_utcnow(),
                    )
                )
            version = 1
        _verify_schema(engine)
        status = SchemaStatus(True, version, None)
    except Exception as e:
        status = SchemaStatus(False, version, str(e)[:1000])
    _set_schema_globals(status)
    return status


class MaintenanceController:
    """Persistent epoch fence plus leases held across side-effect boundaries."""

    def __init__(self, engine=None):
        self.engine = engine or get_engine()
        _ensure_control_row(self.engine)

    def status(self):
        with self.engine.connect() as conn:
            row = conn.execute(
                select(acquisition_maintenance).where(acquisition_maintenance.c.control_id == CONTROL_ID)
            ).one()
            active_leases = conn.execute(
                select(func.count())
                .select_from(acquisition_maintenance_leases)
                .where(acquisition_maintenance_leases.c.released_at.is_(None))
            ).scalar_one()
        values = row._mapping
        return FenceStatus(
            active=bool(values["active"]),
            epoch=int(values["epoch"]),
            owner=values["owner"],
            run_id=values["run_id"],
            reason=values["reason"],
            heartbeat_at=values["heartbeat_at"],
            active_leases=int(active_leases),
        )

    def acquire_fence(self, owner, run_id, reason):
        if not owner or not run_id or not reason:
            raise ValueError("owner, run_id, and reason are required")
        now = _utcnow()
        with self.engine.begin() as conn:
            row = conn.execute(
                select(acquisition_maintenance)
                .where(acquisition_maintenance.c.control_id == CONTROL_ID)
                .with_for_update()
            ).one()
            current = row._mapping
            if current["active"]:
                if current["owner"] == str(owner) and current["run_id"] == str(run_id):
                    return self.status()
                raise MaintenanceConflict("acquisition maintenance is owned by another operation")
            epoch = int(current["epoch"]) + 1
            result = conn.execute(
                update(acquisition_maintenance)
                .where(acquisition_maintenance.c.control_id == CONTROL_ID)
                .where(acquisition_maintenance.c.epoch == current["epoch"])
                .where(acquisition_maintenance.c.active == 0)
                .values(
                    epoch=epoch,
                    active=1,
                    owner=str(owner),
                    run_id=str(run_id),
                    reason=str(reason)[:1000],
                    acquired_at=now,
                    heartbeat_at=now,
                    released_at=None,
                )
            )
            if result.rowcount != 1:
                raise MaintenanceConflict("acquisition maintenance fence changed concurrently")
            conn.execute(
                insert(acquisition_maintenance_events).values(
                    epoch=epoch,
                    action="acquire",
                    actor=str(owner),
                    run_id=str(run_id),
                    reason=str(reason)[:1000],
                    created_at=now,
                )
            )
        return self.status()

    def heartbeat_fence(self, owner, run_id, epoch):
        with self.engine.begin() as conn:
            result = conn.execute(
                update(acquisition_maintenance)
                .where(acquisition_maintenance.c.control_id == CONTROL_ID)
                .where(acquisition_maintenance.c.active == 1)
                .where(acquisition_maintenance.c.owner == str(owner))
                .where(acquisition_maintenance.c.run_id == str(run_id))
                .where(acquisition_maintenance.c.epoch == int(epoch))
                .values(heartbeat_at=_utcnow())
            )
        if result.rowcount != 1:
            raise MaintenanceConflict("maintenance fence ownership changed")

    def release_fence(self, owner, run_id, epoch):
        status = self.status()
        if status.active_leases:
            raise MaintenanceConflict("cannot release maintenance fence before active leases drain")
        now = _utcnow()
        with self.engine.begin() as conn:
            result = conn.execute(
                update(acquisition_maintenance)
                .where(acquisition_maintenance.c.control_id == CONTROL_ID)
                .where(acquisition_maintenance.c.active == 1)
                .where(acquisition_maintenance.c.owner == str(owner))
                .where(acquisition_maintenance.c.run_id == str(run_id))
                .where(acquisition_maintenance.c.epoch == int(epoch))
                .values(
                    active=0,
                    owner=None,
                    run_id=None,
                    reason=None,
                    heartbeat_at=now,
                    released_at=now,
                )
            )
            if result.rowcount != 1:
                raise MaintenanceConflict("maintenance fence ownership changed")
            conn.execute(
                insert(acquisition_maintenance_events).values(
                    epoch=int(epoch),
                    action="release",
                    actor=str(owner),
                    run_id=str(run_id),
                    reason="completed",
                    created_at=now,
                )
            )
        return self.status()

    def abort_fence(self, actor, reason):
        if not actor or not reason:
            raise ValueError("actor and reason are required for an audited abort")
        status = self.status()
        if not status.active:
            raise MaintenanceConflict("no active acquisition maintenance fence")
        if status.active_leases:
            raise MaintenanceConflict("cannot abort while side-effect leases are active")
        now = _utcnow()
        with self.engine.begin() as conn:
            result = conn.execute(
                update(acquisition_maintenance)
                .where(acquisition_maintenance.c.control_id == CONTROL_ID)
                .where(acquisition_maintenance.c.active == 1)
                .where(acquisition_maintenance.c.epoch == status.epoch)
                .values(
                    active=0,
                    owner=None,
                    run_id=None,
                    reason=None,
                    heartbeat_at=now,
                    released_at=now,
                )
            )
            if result.rowcount != 1:
                raise MaintenanceConflict("maintenance fence changed during abort")
            conn.execute(
                insert(acquisition_maintenance_events).values(
                    epoch=status.epoch,
                    action="abort",
                    actor=str(actor),
                    run_id=status.run_id,
                    reason=str(reason)[:1000],
                    created_at=now,
                )
            )
        return self.status()

    def acquire_lease(self, owner, work_kind, entity_type=None, entity_id=None, lease_id=None):
        if not owner or not work_kind:
            raise ValueError("owner and work_kind are required")
        if _operator_requested(getattr(comicarr, "CONFIG", None)):
            raise MaintenanceBlocked("operator acquisition maintenance is enabled")
        lease_id = str(lease_id or uuid.uuid4())
        now = _utcnow()
        columns = [
            acquisition_maintenance_leases.c.lease_id,
            acquisition_maintenance_leases.c.epoch,
            acquisition_maintenance_leases.c.owner,
            acquisition_maintenance_leases.c.work_kind,
            acquisition_maintenance_leases.c.entity_type,
            acquisition_maintenance_leases.c.entity_id,
            acquisition_maintenance_leases.c.acquired_at,
            acquisition_maintenance_leases.c.heartbeat_at,
            acquisition_maintenance_leases.c.released_at,
        ]
        gated_values = select(
            literal(lease_id),
            acquisition_maintenance.c.epoch,
            literal(str(owner)),
            literal(str(work_kind)),
            literal(str(entity_type) if entity_type is not None else None),
            literal(str(entity_id) if entity_id is not None else None),
            literal(now),
            literal(now),
            literal(None),
        ).where(
            acquisition_maintenance.c.control_id == CONTROL_ID,
            acquisition_maintenance.c.active == 0,
        )
        try:
            with self.engine.begin() as conn:
                result = conn.execute(insert(acquisition_maintenance_leases).from_select(columns, gated_values))
        except IntegrityError:
            result = None
        with self.engine.connect() as conn:
            row = conn.execute(
                select(acquisition_maintenance_leases).where(
                    acquisition_maintenance_leases.c.lease_id == lease_id,
                    acquisition_maintenance_leases.c.released_at.is_(None),
                )
            ).first()
        if row is None or (result is not None and result.rowcount == 0):
            raise MaintenanceBlocked("acquisition maintenance blocks new work claims")
        values = row._mapping
        if values["owner"] != str(owner) or values["work_kind"] != str(work_kind):
            raise MaintenanceConflict("lease_id belongs to a different acquisition claim")
        return Lease(
            lease_id=lease_id,
            epoch=int(values["epoch"]),
            owner=values["owner"],
            work_kind=values["work_kind"],
            entity_type=values["entity_type"],
            entity_id=values["entity_id"],
        )

    def heartbeat_lease(self, lease_id):
        with self.engine.begin() as conn:
            result = conn.execute(
                update(acquisition_maintenance_leases)
                .where(acquisition_maintenance_leases.c.lease_id == str(lease_id))
                .where(acquisition_maintenance_leases.c.released_at.is_(None))
                .values(heartbeat_at=_utcnow())
            )
        if result.rowcount != 1:
            raise MaintenanceConflict("acquisition lease is no longer active")

    def assert_lease_current(self, lease):
        """Fence-token check immediately before an external side effect.

        The caller keeps the lease until that boundary completes. If a fence
        activates after this check, maintenance observes the active lease and
        must drain it before applying database mutations.
        """

        stmt = (
            select(acquisition_maintenance_leases.c.lease_id)
            .select_from(
                acquisition_maintenance_leases.join(
                    acquisition_maintenance,
                    acquisition_maintenance.c.control_id == CONTROL_ID,
                )
            )
            .where(
                acquisition_maintenance_leases.c.lease_id == str(lease.lease_id),
                acquisition_maintenance_leases.c.epoch == int(lease.epoch),
                acquisition_maintenance_leases.c.released_at.is_(None),
                acquisition_maintenance.c.epoch == int(lease.epoch),
                acquisition_maintenance.c.active == 0,
            )
        )
        with self.engine.connect() as conn:
            current = conn.execute(stmt).first()
        if current is None:
            raise MaintenanceBlocked("acquisition lease was fenced before the side effect")
        return True

    def release_lease(self, lease_id):
        now = _utcnow()
        with self.engine.begin() as conn:
            result = conn.execute(
                update(acquisition_maintenance_leases)
                .where(acquisition_maintenance_leases.c.lease_id == str(lease_id))
                .where(acquisition_maintenance_leases.c.released_at.is_(None))
                .values(heartbeat_at=now, released_at=now)
            )
        return result.rowcount == 1

    @contextmanager
    def lease(self, owner, work_kind, entity_type=None, entity_id=None, lease_id=None):
        claim = self.acquire_lease(owner, work_kind, entity_type, entity_id, lease_id)
        try:
            yield claim
        finally:
            self.release_lease(claim.lease_id)

    def list_events(self):
        with self.engine.connect() as conn:
            return [
                dict(row._mapping)
                for row in conn.execute(
                    select(acquisition_maintenance_events).order_by(acquisition_maintenance_events.c.event_id)
                )
            ]


def _operator_requested(config=None):
    return _truthy(os.environ.get("COMICARR_ACQUISITION_MAINTENANCE")) or bool(
        getattr(config, "ACQUISITION_MAINTENANCE", False)
    )


def refresh_runtime_state(config=None, engine=None):
    """Refresh the fail-closed startup/claim projection used by adapters."""

    schema_ready = bool(getattr(comicarr, "ACQUISITION_SCHEMA_READY", False))
    if not schema_ready:
        status = RuntimeGateStatus(True, "schema_unavailable", False, False, 0)
    elif _operator_requested(config):
        fence = MaintenanceController(engine).status()
        status = RuntimeGateStatus(
            True,
            "operator_maintenance",
            True,
            fence.active,
            fence.epoch,
            fence.owner,
            fence.run_id,
            fence.heartbeat_at,
        )
    else:
        fence = MaintenanceController(engine).status()
        status = RuntimeGateStatus(
            fence.active,
            "persistent_maintenance" if fence.active else None,
            True,
            fence.active,
            fence.epoch,
            fence.owner,
            fence.run_id,
            fence.heartbeat_at,
        )
    comicarr.ACQUISITION_WORKERS_BLOCKED = status.blocked
    comicarr.ACQUISITION_BLOCK_REASON = status.reason
    return status
