#  Copyright (C) 2025–2026 Comicarr contributors
#
#  This file is part of Comicarr.
#
#  Comicarr is free software: you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.

"""#483 — needs-attention band resolution actions.

Seams under test (agreed):
  1. journal.read_needs_attention / stamp_resolution
  2. ignore_issue intent helper
  3. search_issue scoped entry
  4. service actions: retry / search-again / ignore / import
  5. acquisition_repair evidence skips resolved statuses
  6. same-provider re-snatch: SNATCHED against failed wins
"""

import queue as queuelib
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import select

import comicarr
from comicarr import db
from comicarr.app.acquisition.maintenance import ensure_acquisition_schema
from comicarr.app.core.context import AppContext
from comicarr.app.downloads import journal
from comicarr.app.downloads import service as dl_service
from comicarr.app.search import service as search_service
from comicarr.app.series import queries as series_queries
from comicarr.app.system.acquisition_repair import RepairService
from comicarr.db import get_engine, shutdown_engine
from comicarr.tables import comics, issues, metadata, pipeline_journal


@pytest.fixture(autouse=True)
def _isolated_db(tmp_path, monkeypatch):
    monkeypatch.setattr(comicarr, "DATA_DIR", str(tmp_path))
    shutdown_engine()
    monkeypatch.delenv("DATABASE_URL", raising=False)
    if not hasattr(comicarr, "LOG_LEVEL") or comicarr.LOG_LEVEL is None:
        monkeypatch.setattr(comicarr, "LOG_LEVEL", 0, raising=False)
    monkeypatch.setattr(comicarr, "GLOBAL_MESSAGES", None, raising=False)
    monkeypatch.setattr(comicarr, "PROVIDER_BLOCKLIST", {}, raising=False)
    monkeypatch.setattr(comicarr, "SEARCH_QUEUE", queuelib.Queue(), raising=False)
    monkeypatch.setattr(
        comicarr,
        "CONFIG",
        SimpleNamespace(
            FAILED_DOWNLOAD_HANDLING=True,
            FAILED_AUTO=False,
            HIGHCOUNT=0,
            DDL_LOCATION=str(tmp_path / "ddl"),
            CACHE_DIR=str(tmp_path / "cache"),
            DESTINATION_DIR=str(tmp_path / "library"),
        ),
        raising=False,
    )
    engine = get_engine()
    metadata.create_all(engine)
    assert ensure_acquisition_schema(engine).ready
    yield
    shutdown_engine()


def _seed_issue(*, issueid="1001", comicid="C1", status="Failed", intent=None):
    with get_engine().begin() as conn:
        conn.execute(
            comics.insert().values(
                ComicID=comicid,
                ComicName="Saga",
                ComicYear="2012",
                Status="Active",
            )
        )
        conn.execute(
            issues.insert().values(
                IssueID=issueid,
                ComicID=comicid,
                ComicName="Saga",
                Issue_Number="1",
                Status=status,
                AcquisitionIntent=intent,
            )
        )


def _seed_failed_row(
    *,
    key="1001|nzbgeek",
    issueid="1001",
    provider="nzbgeek",
    status=None,
    retry_count=None,
    payload=None,
):
    journal.record_transition(
        key,
        journal.SNATCHED,
        payload=payload
        or {
            "issueid": issueid,
            "provider": provider,
            "nzbname": "Saga.001",
            "comicname": "Saga",
            "issuenumber": "1",
        },
        issueid=issueid,
        provider=provider,
        nzbname="Saga.001",
    )
    journal.mark_failed(key, "download_failed_no_auto_handling", issueid=issueid, provider=provider)
    if status is not None or retry_count is not None:
        with get_engine().begin() as conn:
            values = {}
            if status is not None:
                values["status"] = status
            if retry_count is not None:
                values["retry_count"] = retry_count
            conn.execute(
                pipeline_journal.update().where(pipeline_journal.c.release_key == key).values(**values)
            )
    return key


def _seed_manual_review_row(
    *,
    key="1001|ddl",
    issueid="1001",
    provider="ddl",
    nzb_name="Saga.001.cbz",
    nzb_folder=None,
):
    payload = {
        "issueid": issueid,
        "provider": provider,
        "nzb_name": nzb_name,
        "nzbname": nzb_name,
        "nzb_folder": nzb_folder or "/tmp/pp/Saga.001",
    }
    journal.record_transition(
        key,
        journal.SNATCHED,
        payload=payload,
        issueid=issueid,
        provider=provider,
        nzbname=nzb_name,
    )
    journal.record_transition(key, journal.DOWNLOADED, payload=payload)
    journal.mark_manual_review(key, "path_unsafe", payload=payload, issueid=issueid, provider=provider)
    return key


def _issue_row(issueid="1001"):
    return db.select_one(select(issues).where(issues.c.IssueID == issueid))


def _journal_row(key):
    return journal.read_one(key)


# ---------------------------------------------------------------------------
# 1. Band query + stamp_resolution
# ---------------------------------------------------------------------------


def test_read_needs_attention_settled_predicate():
    _seed_issue()
    on_band = _seed_failed_row(key="1001|a")
    off_retried = _seed_failed_row(key="1001|b", status=journal.STATUS_RETRIED)
    off_ignored = _seed_failed_row(key="1001|c", status=journal.STATUS_IGNORED)
    off_imported = _seed_failed_row(key="1001|d", status=journal.STATUS_IMPORTED)
    open_key = journal.release_key("1001", "open")
    journal.record_transition(open_key, journal.SNATCHED, issueid="1001", provider="open")

    keys = {r["release_key"] for r in journal.read_needs_attention()}
    assert on_band in keys
    assert off_retried not in keys
    assert off_ignored not in keys
    assert off_imported not in keys
    assert open_key not in keys


def test_stamp_resolution_retried_increments_retry_count_without_stage_change():
    _seed_issue()
    key = _seed_failed_row()
    before = _journal_row(key)
    assert before["stage"] == journal.FAILED
    assert before.get("retry_count") in (None, 0)

    assert journal.stamp_resolution(key, journal.STATUS_RETRIED, increment_retry=True) is True

    after = _journal_row(key)
    assert after["stage"] == journal.FAILED
    assert after["stage_rank"] == before["stage_rank"]
    assert after["status"] == journal.STATUS_RETRIED
    assert after["retry_count"] == 1
    assert key not in {r["release_key"] for r in journal.read_needs_attention()}


def test_stamp_resolution_rejects_open_stage():
    key = journal.release_key("9", "p")
    journal.record_transition(key, journal.SNATCHED, issueid="9", provider="p")
    assert journal.stamp_resolution(key, journal.STATUS_IGNORED) is False
    assert _journal_row(key)["stage"] == journal.SNATCHED
    assert _journal_row(key).get("status") is None


# ---------------------------------------------------------------------------
# 6. Same-provider re-snatch (SNATCHED against failed wins)
# ---------------------------------------------------------------------------


def test_snatched_against_failed_resets_and_wins():
    """NZB/torrent snatch path writes SNATCHED, not RESERVED — must not silent-no-op."""
    key = journal.release_key("500", "nzbgeek")
    journal.record_transition(key, journal.SNATCHED, issueid="500", provider="nzbgeek")
    journal.mark_failed(key, "gone")
    journal.stamp_resolution(key, journal.STATUS_RETRIED, increment_retry=True)

    won = journal.record_transition(
        key,
        journal.SNATCHED,
        payload={"issueid": "500", "provider": "nzbgeek", "nzbname": "retry.cbz"},
        issueid="500",
        provider="nzbgeek",
        nzbname="retry.cbz",
    )

    assert won is True
    row = _journal_row(key)
    assert row["stage"] == journal.SNATCHED
    assert row["fail_reason"] is None
    assert row.get("status") is None  # reset clears resolution stamp for new attempt


# ---------------------------------------------------------------------------
# 2. ignore_issue
# ---------------------------------------------------------------------------


def test_ignore_issue_sets_ignored_intent_and_status():
    _seed_issue(status="Failed")
    series_queries.ignore_issue("1001", "operator")
    row = _issue_row()
    assert row["AcquisitionIntent"] == "ignored"
    assert row["Status"] == "Ignored"


def test_ignore_issue_requires_audit_identity():
    _seed_issue()
    with pytest.raises(ValueError, match="audit identity"):
        series_queries.ignore_issue("1001", "")


# ---------------------------------------------------------------------------
# 3. search_issue
# ---------------------------------------------------------------------------


def test_search_issue_blocked_when_no_viable_route(monkeypatch):
    ctx = AppContext(config=comicarr.CONFIG, provider_blocklist={})
    monkeypatch.setattr(
        "comicarr.app.search.health.get_search_health",
        lambda *a, **k: {"viable_route": False, "routes": {}},
    )
    result = search_service.search_issue(ctx, "1001")
    assert result["success"] is False
    assert result["status"] == "blocked"


def test_search_issue_enqueues_when_route_ready(monkeypatch):
    ctx = AppContext(config=comicarr.CONFIG, provider_blocklist={})
    monkeypatch.setattr(
        "comicarr.app.search.health.get_search_health",
        lambda *a, **k: {
            "viable_route": True,
            "routes": {"nzb": {"ready": True, "viable": True}},
        },
    )
    fake_cmd = SimpleNamespace(run_id="run-1", issueid="1001")
    with patch("comicarr.app.search.commands.enqueue_search_command", return_value=fake_cmd) as enq:
        result = search_service.search_issue(ctx, "1001", trigger="band_retry")
    assert result["success"] is True
    assert result["run_id"] == "run-1"
    enq.assert_called_once()
    assert enq.call_args.kwargs["trigger"] == "band_retry"


# ---------------------------------------------------------------------------
# 4. Service actions
# ---------------------------------------------------------------------------


def test_retry_failed_wants_stamps_and_searches(monkeypatch):
    _seed_issue(status="Failed")
    key = _seed_failed_row()
    ctx = AppContext(config=comicarr.CONFIG, provider_blocklist={})
    monkeypatch.setattr(
        "comicarr.app.search.health.get_search_health",
        lambda *a, **k: {"viable_route": True, "routes": {"nzb": {"ready": True}}},
    )
    with patch(
        "comicarr.app.search.commands.enqueue_search_command",
        return_value=SimpleNamespace(run_id="r1", issueid="1001"),
    ):
        result = dl_service.resolve_needs_attention(ctx, key, "retry", audit_identity="op")

    assert result["success"] is True
    assert _issue_row()["Status"] == "Wanted"
    assert _issue_row()["AcquisitionIntent"] == "wanted"
    row = _journal_row(key)
    assert row["status"] == journal.STATUS_RETRIED
    assert row["retry_count"] == 1
    assert row["stage"] == journal.FAILED
    assert key not in {r["release_key"] for r in journal.read_needs_attention()}


def test_retry_blocked_does_not_stamp(monkeypatch):
    _seed_issue(status="Failed")
    key = _seed_failed_row()
    ctx = AppContext(config=comicarr.CONFIG, provider_blocklist={})
    monkeypatch.setattr(
        "comicarr.app.search.health.get_search_health",
        lambda *a, **k: {"viable_route": False, "routes": {}},
    )
    result = dl_service.resolve_needs_attention(ctx, key, "retry", audit_identity="op")
    assert result["success"] is False
    assert result["status"] == "blocked"
    assert _journal_row(key).get("status") not in journal.RESOLVED_STATUSES
    assert key in {r["release_key"] for r in journal.read_needs_attention()}


def test_ignore_failed_stamps_and_sets_intent():
    _seed_issue(status="Failed")
    key = _seed_failed_row()
    ctx = AppContext(config=comicarr.CONFIG, provider_blocklist={})
    result = dl_service.resolve_needs_attention(ctx, key, "ignore", audit_identity="op")
    assert result["success"] is True
    assert _issue_row()["AcquisitionIntent"] == "ignored"
    assert _issue_row()["Status"] == "Ignored"
    assert _journal_row(key)["status"] == journal.STATUS_IGNORED
    assert _journal_row(key)["stage"] == journal.FAILED


def test_search_again_manual_review(monkeypatch):
    _seed_issue(status="Snatched")
    key = _seed_manual_review_row()
    ctx = AppContext(config=comicarr.CONFIG, provider_blocklist={})
    monkeypatch.setattr(
        "comicarr.app.search.health.get_search_health",
        lambda *a, **k: {"viable_route": True, "routes": {"nzb": {"ready": True}}},
    )
    with patch(
        "comicarr.app.search.commands.enqueue_search_command",
        return_value=SimpleNamespace(run_id="r2", issueid="1001"),
    ):
        result = dl_service.resolve_needs_attention(ctx, key, "search_again", audit_identity="op")
    assert result["success"] is True
    assert _issue_row()["Status"] == "Wanted"
    assert _journal_row(key)["status"] == journal.STATUS_RETRIED
    assert _journal_row(key)["stage"] == journal.MANUAL_REVIEW


def test_import_stamps_only_on_success(tmp_path, monkeypatch):
    _seed_issue()
    root = tmp_path / "pp"
    root.mkdir()
    folder = root / "job"
    folder.mkdir()
    key = _seed_manual_review_row(nzb_folder=str(folder), nzb_name="Saga.001.cbz")
    monkeypatch.setattr(
        comicarr,
        "CONFIG",
        SimpleNamespace(
            FAILED_DOWNLOAD_HANDLING=True,
            FAILED_AUTO=False,
            HIGHCOUNT=0,
            DDL_LOCATION=str(tmp_path / "ddl"),
            CACHE_DIR=str(tmp_path / "cache"),
            DESTINATION_DIR=str(tmp_path / "library"),
            MANUAL_PP_FOLDER=str(root),
        ),
        raising=False,
    )
    monkeypatch.setattr(comicarr, "PP_QUEUE", queuelib.Queue(), raising=False)
    ctx = AppContext(config=comicarr.CONFIG, provider_blocklist={})

    result = dl_service.resolve_needs_attention(ctx, key, "import", audit_identity="op")
    assert result["success"] is True
    assert _journal_row(key)["status"] == journal.STATUS_IMPORTED
    assert _journal_row(key)["stage"] == journal.MANUAL_REVIEW
    assert not comicarr.PP_QUEUE.empty()
    queued = comicarr.PP_QUEUE.get_nowait()
    assert "journal_release_key" not in queued


def test_import_validation_failure_keeps_band(tmp_path, monkeypatch):
    _seed_issue()
    # folder outside any configured root / missing
    key = _seed_manual_review_row(nzb_folder=str(tmp_path / "evil" / "path"), nzb_name="Saga.001.cbz")
    monkeypatch.setattr(
        comicarr,
        "CONFIG",
        SimpleNamespace(
            MANUAL_PP_FOLDER=str(tmp_path / "pp"),
            DDL_LOCATION=str(tmp_path / "ddl"),
            CACHE_DIR=str(tmp_path / "cache"),
            DESTINATION_DIR=str(tmp_path / "library"),
        ),
        raising=False,
    )
    ctx = AppContext(config=comicarr.CONFIG, provider_blocklist={})
    result = dl_service.resolve_needs_attention(ctx, key, "import", audit_identity="op")
    assert result["success"] is False
    assert "error" in result
    assert _journal_row(key).get("status") != journal.STATUS_IMPORTED
    assert key in {r["release_key"] for r in journal.read_needs_attention()}


def test_retry_not_allowed_on_manual_review():
    _seed_issue()
    key = _seed_manual_review_row()
    ctx = AppContext(config=comicarr.CONFIG, provider_blocklist={})
    result = dl_service.resolve_needs_attention(ctx, key, "retry", audit_identity="op")
    assert result["success"] is False


def test_import_not_allowed_on_failed():
    _seed_issue()
    key = _seed_failed_row()
    ctx = AppContext(config=comicarr.CONFIG, provider_blocklist={})
    result = dl_service.resolve_needs_attention(ctx, key, "import", audit_identity="op")
    assert result["success"] is False


def test_already_resolved_returns_409_without_side_effects(monkeypatch):
    _seed_issue(status="Failed")
    key = _seed_failed_row(status=journal.STATUS_RETRIED, retry_count=1)
    ctx = AppContext(config=comicarr.CONFIG, provider_blocklist={})
    enqueued = []
    monkeypatch.setattr(
        "comicarr.app.search.commands.enqueue_search_command",
        lambda *a, **k: enqueued.append(1) or SimpleNamespace(run_id="x", issueid="1001"),
    )
    result = dl_service.resolve_needs_attention(ctx, key, "retry", audit_identity="op")
    assert result["success"] is False
    assert result.get("status_code") == 409
    assert enqueued == []
    assert _issue_row()["Status"] == "Failed"
    assert _journal_row(key)["status"] == journal.STATUS_RETRIED


# ---------------------------------------------------------------------------
# 5. Repair evidence skips resolved statuses
# ---------------------------------------------------------------------------


def test_journal_evidence_skips_retried_failed_row():
    _seed_issue(status="Wanted", intent="wanted")
    key = _seed_failed_row(status=journal.STATUS_RETRIED)
    service = RepairService(get_engine())
    with get_engine().connect() as conn:
        evidence = service._journal_evidence(conn, "1001")
    assert evidence is None or evidence.get("reason") != "journal_failed"
    # If another journal row existed we might get different evidence; with only
    # the resolved failed row, evidence must not propose Failed.
    if evidence is not None:
        assert evidence.get("target_status") != "Failed"
    # Explicit: resolved row alone yields no journal evidence.
    with get_engine().begin() as conn:
        conn.execute(pipeline_journal.delete().where(pipeline_journal.c.release_key == key))
    # re-seed only resolved failed
    _seed_failed_row(key=key, status=journal.STATUS_RETRIED)
    with get_engine().connect() as conn:
        assert service._journal_evidence(conn, "1001") is None
