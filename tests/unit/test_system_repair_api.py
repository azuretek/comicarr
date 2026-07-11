#  Copyright (C) 2025–2026 Comicarr contributors
#
#  This file is part of Comicarr.
#
#  Comicarr is free software: you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.

"""System service wrappers for acquisition repair endpoints."""

from types import SimpleNamespace
from unittest.mock import MagicMock

from comicarr.app.core.context import AppContext
from comicarr.app.system import service as system_service
from comicarr.app.system.acquisition_repair import RepairConfirmationError


def _ctx():
    return AppContext(config=SimpleNamespace())


def test_preview_acquisition_repair_returns_success_payload(monkeypatch):
    preview = MagicMock(
        return_value={
            "run_id": "run-1",
            "preview_token": "token",
            "fingerprint": "fp",
            "summary": {"selected": 1},
            "items": [],
        }
    )
    monkeypatch.setattr(
        system_service,
        "_repair_service",
        lambda: SimpleNamespace(preview_series=preview),
    )

    result = system_service.preview_acquisition_repair(
        _ctx(),
        "160294",
        actor="frankie",
        session_id="session-1",
    )

    assert result["success"] is True
    assert result["run_id"] == "run-1"
    preview.assert_called_once()


def test_confirm_acquisition_repair_maps_confirmation_errors(monkeypatch):
    confirm = MagicMock(side_effect=RepairConfirmationError("preview token expired"))
    monkeypatch.setattr(
        system_service,
        "_repair_service",
        lambda: SimpleNamespace(confirm=confirm),
    )

    result = system_service.confirm_acquisition_repair(
        _ctx(),
        "run-1",
        actor="frankie",
        session_id="session-1",
        preview_token="bad",
        fingerprint="fp",
    )

    assert result["success"] is False
    assert result["status_code"] == 409
    assert "expired" in result["error"]


def test_get_acquisition_repair_run_authorizes_session(monkeypatch):
    read_public_run = MagicMock(
        return_value={
            "run": {
                "run_id": "run-1",
                "scope_type": "series",
                "scope_id": "160294",
                "state": "previewed",
                "item_count": 0,
                "selected_count": 0,
                "applied_count": 0,
                "conflict_count": 0,
                "rollback_count": 0,
                "rollback_conflict_count": 0,
                "last_sequence": 0,
                "created_at": "t0",
                "confirmed_at": None,
                "started_at": None,
                "completed_at": None,
            },
            "items": [],
        }
    )
    service = SimpleNamespace(
        read_public_run=read_public_run,
    )
    monkeypatch.setattr(system_service, "_repair_service", lambda: service)

    result = system_service.get_acquisition_repair_run(
        _ctx(),
        "run-1",
        actor="frankie",
        session_id="session-1",
    )

    assert result["success"] is True
    assert result["run"]["run_id"] == "run-1"
    read_public_run.assert_called_once_with(
        "run-1",
        actor="frankie",
        session_id="session-1",
        include_items=True,
    )


def test_get_acquisition_repair_run_can_omit_manifest_items(monkeypatch):
    read_public_run = MagicMock(return_value={"run": {"run_id": "run-1"}, "items": []})
    monkeypatch.setattr(system_service, "_repair_service", lambda: SimpleNamespace(read_public_run=read_public_run))

    result = system_service.get_acquisition_repair_run(
        _ctx(),
        "run-1",
        actor="frankie",
        session_id="session-1",
        include_items=False,
    )

    assert result == {"success": True, "run": {"run_id": "run-1"}, "items": []}
    read_public_run.assert_called_once_with(
        "run-1",
        actor="frankie",
        session_id="session-1",
        include_items=False,
    )


def test_abort_acquisition_maintenance_is_reasoned_and_audited(monkeypatch):
    controller = SimpleNamespace(
        abort_fence=MagicMock(
            return_value=SimpleNamespace(
                active=False,
                epoch=4,
                owner=None,
                run_id=None,
                reason=None,
                heartbeat_at="2026-07-10T12:00:00+00:00",
                active_leases=0,
            )
        )
    )
    monkeypatch.setattr("comicarr.app.acquisition.maintenance.MaintenanceController", lambda _engine: controller)
    monkeypatch.setattr(system_service.db, "get_engine", lambda: object())
    monkeypatch.setattr(
        "comicarr.app.acquisition.maintenance.get_reconciliation_status",
        lambda _engine: {"state": "ready"},
    )
    monkeypatch.setattr(
        "comicarr.app.acquisition.maintenance.refresh_runtime_state",
        lambda *_args: SimpleNamespace(as_dict=lambda: {"state": "ready"}),
    )

    missing_reason = system_service.abort_acquisition_maintenance(_ctx(), actor="frankie", reason="")
    result = system_service.abort_acquisition_maintenance(
        _ctx(), actor="frankie", reason="confirmed no active downloader work"
    )

    assert missing_reason["status_code"] == 400
    assert result["success"] is True
    assert result["maintenance"] == {
        "active": False,
        "epoch": 4,
        "owner": None,
        "run_id": None,
        "reason": None,
        "heartbeat_at": "2026-07-10T12:00:00+00:00",
        "active_leases": 0,
    }
    controller.abort_fence.assert_called_once_with(
        "frankie", "confirmed no active downloader work", force_stale_leases=False
    )
