#  Copyright (C) 2025–2026 Comicarr contributors
#
#  This file is part of Comicarr.
#
#  Comicarr is free software: you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.

import queue
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
import requests
from sqlalchemy import insert, select

import comicarr
from comicarr import db, getcomics
from comicarr.app.downloads import recovery, router, service
from comicarr.app.downloads.ddl_commands import DDLCommand
from comicarr.downloaders import mediafire
from comicarr.tables import ddl_info, metadata


def _complete_ddl_payload(**overrides):
    payload = {
        "id": "ddl-1",
        "link": "https://downloads.invalid/issue.cbz",
        "site": "DDL(GetComics)",
        "series": "Saga",
        "year": "2026",
        "size": "10 MB",
        "comicid": "comic-1",
        "issueid": "issue-1",
        "oneoff": False,
        "link_type": "GC-Main",
        "filename": "Saga 001.cbz",
        "mainlink": "https://getcomics.invalid/saga",
        "comicinfo": [{"pack": False, "IssueID": "issue-1"}],
        "packinfo": None,
        "remote_filesize": 10_485_760,
        "resume": None,
        "issues": "1",
        "pack": False,
    }
    payload.update(overrides)
    return payload


@pytest.fixture
def sqlite_ddl_db(tmp_path, monkeypatch):
    monkeypatch.setattr(comicarr, "DATA_DIR", str(tmp_path))
    db.shutdown_engine()
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setattr(
        comicarr,
        "CONFIG",
        SimpleNamespace(
            DDL_LOCATION=str(tmp_path / "downloads"),
            CACHE_DIR=str(tmp_path / "cache"),
            ENFORCE_PERMS=False,
            CHMOD_FILE="0660",
            CHMOD_DIR="0777",
        ),
    )
    engine = db.get_engine()
    metadata.create_all(engine)
    yield engine
    db.shutdown_engine()


def test_process_issue_passes_issueid_by_keyword(monkeypatch):
    process_instance = MagicMock()
    process_class = MagicMock(return_value=process_instance)
    monkeypatch.setattr(service.process, "Process", process_class)

    result = service.process_issue("comic-1", "/downloads/Saga", issueid="issue-1")

    assert result["success"] is True
    process_class.assert_called_once_with(
        nzb_name="comic-1",
        nzb_folder="/downloads/Saga",
        issueid="issue-1",
    )


def test_queue_ddl_persists_reconstructable_command_before_enqueue(monkeypatch):
    operations = []
    persisted = {}
    queued = MagicMock()

    def fake_upsert(table, values, controls):
        operations.append("persist")
        persisted.update(values)
        assert table == "ddl_info"
        assert controls == {"ID": "ddl-1"}

    queued.put.side_effect = lambda item: operations.append(("enqueue", item))
    monkeypatch.setattr(service.db, "upsert", fake_upsert)
    monkeypatch.setattr(comicarr, "DDL_QUEUE", queued)

    result = service.queue_ddl_download(_complete_ddl_payload())

    assert result["success"] is True, result
    assert operations[0] == "persist"
    command = operations[1][1]
    assert command == _complete_ddl_payload()
    assert persisted["status"] == "Queued"
    assert persisted["oneoff"] == 0
    assert persisted["resume"] is None
    assert persisted["comicinfo"]
    assert persisted["packinfo"] is None
    assert DDLCommand.from_mapping({"ID": "ddl-1", **persisted}).to_queue_item() == _complete_ddl_payload()


def test_queue_ddl_keeps_persisted_row_queued_when_handoff_fails(monkeypatch):
    statuses = []
    monkeypatch.setattr(service.db, "upsert", MagicMock())
    monkeypatch.setattr(
        service.dl_queries,
        "update_ddl_status",
        lambda item_id, status: statuses.append((item_id, status)),
    )
    ddl_queue = MagicMock()
    ddl_queue.put.side_effect = RuntimeError("queue unavailable")
    monkeypatch.setattr(comicarr, "DDL_QUEUE", ddl_queue)

    result = service.queue_ddl_download(_complete_ddl_payload())

    assert result["success"] is False
    assert result["handoff_error"] is True
    assert statuses == []


def test_real_sqlite_mediafire_path_updates_ddl_row(sqlite_ddl_db, tmp_path):
    download_dir = tmp_path / "downloads"
    download_dir.mkdir()
    with sqlite_ddl_db.begin() as conn:
        conn.execute(insert(ddl_info).values(ID="ddl-real", status="Downloading"))

    downloader = mediafire.MediaFire.__new__(mediafire.MediaFire)
    downloader.dl_location = str(download_dir)
    downloader.session = MagicMock(
        get=MagicMock(return_value=SimpleNamespace(iter_content=lambda chunk_size: iter([b"comic"])))
    )

    downloader.mediafire_dl(
        "https://downloads.invalid/issue.cbz",
        "ddl-real",
        {"filename": "issue.cbz", "filesize": 5},
        "issue-1",
    )

    with sqlite_ddl_db.connect() as conn:
        row = conn.execute(select(ddl_info).where(ddl_info.c.ID == "ddl-real")).mappings().one()
    assert row["tmp_filename"] == "issue.cbz"


@pytest.mark.parametrize(
    ("payload", "expected_error"),
    [
        ({"id": "ddl-1", "link": "https://example.invalid", "site": "DDL(GetComics)"}, "Missing"),
        (_complete_ddl_payload(site="DDL(Unknown)"), "Unsupported"),
        (_complete_ddl_payload(link_type="GC-Unknown"), "Unsupported"),
    ],
)
def test_queue_ddl_rejects_poison_jobs_before_mutation(monkeypatch, payload, expected_error):
    upsert = MagicMock()
    ddl_queue = MagicMock()
    monkeypatch.setattr(service.db, "upsert", upsert)
    monkeypatch.setattr(comicarr, "DDL_QUEUE", ddl_queue)

    result = service.queue_ddl_download(payload)

    assert result["success"] is False
    assert expected_error.lower() in result["error"].lower()
    upsert.assert_not_called()
    ddl_queue.put.assert_not_called()


def test_queue_ddl_router_returns_400_for_non_runnable_legacy_payload(monkeypatch):
    monkeypatch.setattr(service.db, "upsert", MagicMock())
    monkeypatch.setattr(comicarr, "DDL_QUEUE", MagicMock())

    response = router.queue_ddl_download({"id": "ddl-1", "link": "https://example.invalid", "site": "DDL(GetComics)"})

    assert response.status_code == 400


def test_requeue_reconstructs_and_enqueues_persisted_command(monkeypatch):
    row = _complete_ddl_payload()
    row.update(
        {
            "ID": row.pop("id"),
            "oneoff": 0,
            "remote_filesize": str(row["remote_filesize"]),
            "comicinfo": '[{"pack": false, "IssueID": "issue-1"}]',
            "packinfo": None,
            "status": "Failed",
        }
    )
    ddl_queue = MagicMock()
    statuses = []
    monkeypatch.setattr(service.dl_queries, "get_ddl_item", lambda item_id: row)
    monkeypatch.setattr(service.dl_queries, "update_ddl_status", lambda item_id, status: statuses.append(status))
    monkeypatch.setattr(comicarr, "DDL_QUEUE", ddl_queue)

    result = service.requeue_ddl_item("ddl-1")

    assert result["success"] is True
    ddl_queue.put.assert_called_once_with(_complete_ddl_payload())
    assert statuses == ["Queued"]


def test_requeue_does_not_mark_incomplete_persisted_item_queued(monkeypatch):
    statuses = []
    ddl_queue = MagicMock()
    monkeypatch.setattr(
        service.dl_queries,
        "get_ddl_item",
        lambda item_id: {"ID": item_id, "link": "https://example.invalid", "site": "DDL(GetComics)"},
    )
    monkeypatch.setattr(service.dl_queries, "update_ddl_status", lambda item_id, status: statuses.append(status))
    monkeypatch.setattr(comicarr, "DDL_QUEUE", ddl_queue)

    result = service.requeue_ddl_item("ddl-bad")

    assert result["success"] is False
    assert "missing" in result["error"].lower()
    assert statuses == []
    ddl_queue.put.assert_not_called()


def test_requeue_keeps_durable_queued_status_when_handoff_fails(monkeypatch):
    row = _complete_ddl_payload()
    row.update(
        {
            "ID": row.pop("id"),
            "oneoff": 0,
            "comicinfo": '[{"pack": false, "IssueID": "issue-1"}]',
            "packinfo": None,
            "status": "Failed",
        }
    )
    statuses = []
    ddl_queue = MagicMock()
    ddl_queue.put.side_effect = RuntimeError("queue unavailable")
    monkeypatch.setattr(service.dl_queries, "get_ddl_item", lambda item_id: row)
    monkeypatch.setattr(service.dl_queries, "update_ddl_status", lambda item_id, status: statuses.append(status))
    monkeypatch.setattr(comicarr, "DDL_QUEUE", ddl_queue)

    result = service.requeue_ddl_item("ddl-1")

    assert result["success"] is False
    assert result["handoff_error"] is True
    assert statuses == ["Queued"]


def test_requeue_returns_structured_operational_error(monkeypatch):
    monkeypatch.setattr(
        service.dl_queries,
        "get_ddl_item",
        MagicMock(side_effect=RuntimeError("database unavailable")),
    )

    result = service.requeue_ddl_item("ddl-1")

    assert result["success"] is False
    assert result["operational_error"] is True
    assert result.get("not_found") is not True


@pytest.mark.parametrize(
    ("result", "expected_status"),
    [
        ({"success": False, "error": "missing", "not_found": True}, 404),
        ({"success": False, "error": "invalid", "validation_error": True}, 400),
        ({"success": False, "error": "queue unavailable", "handoff_error": True}, 503),
        ({"success": False, "error": "database unavailable", "operational_error": True}, 500),
    ],
)
def test_requeue_router_maps_structured_failures(monkeypatch, result, expected_status):
    monkeypatch.setattr(service, "requeue_ddl_item", lambda item_id: result)

    response = router.requeue_ddl_item("ddl-1")

    assert response.status_code == expected_status


def _persist_queued_command(command):
    service.db.upsert("ddl_info", DDLCommand.from_mapping(command).to_persisted_values(), {"ID": command["id"]})


def test_startup_sweep_recovers_persisted_and_prejournal_crash(sqlite_ddl_db):
    command = _complete_ddl_payload()
    _persist_queued_command(command)

    first_process_queue = queue.Queue()
    first_result = service.recover_queued_ddl_commands(first_process_queue)
    dequeued_before_journal = first_process_queue.get_nowait()

    assert first_result == {"enqueued_ids": ["ddl-1"], "failed_ids": [], "handoff_failed_ids": []}
    assert dequeued_before_journal == command

    restarted_process_queue = queue.Queue()
    second_result = service.recover_queued_ddl_commands(restarted_process_queue)

    assert second_result["enqueued_ids"] == ["ddl-1"]
    assert restarted_process_queue.get_nowait() == command


def test_startup_sweep_marks_invalid_legacy_row_failed(sqlite_ddl_db):
    with sqlite_ddl_db.begin() as conn:
        conn.execute(
            insert(ddl_info).values(
                ID="ddl-invalid",
                status="Queued",
                link="https://downloads.invalid/issue.cbz",
                site="DDL(GetComics)",
            )
        )
    recovered_queue = queue.Queue()

    result = service.recover_queued_ddl_commands(recovered_queue)

    assert result == {"enqueued_ids": [], "failed_ids": ["ddl-invalid"], "handoff_failed_ids": []}
    assert recovered_queue.empty()
    with sqlite_ddl_db.connect() as conn:
        status = conn.execute(select(ddl_info.c.status).where(ddl_info.c.ID == "ddl-invalid")).scalar_one()
    assert status == "Failed"


def test_startup_sweep_queue_failure_keeps_row_recoverable(sqlite_ddl_db):
    command = _complete_ddl_payload()
    _persist_queued_command(command)
    unavailable_queue = MagicMock()
    unavailable_queue.put.side_effect = RuntimeError("queue unavailable")

    result = service.recover_queued_ddl_commands(unavailable_queue)

    assert result == {"enqueued_ids": [], "failed_ids": [], "handoff_failed_ids": ["ddl-1"]}
    with sqlite_ddl_db.connect() as conn:
        status = conn.execute(select(ddl_info.c.status).where(ddl_info.c.ID == "ddl-1")).scalar_one()
    assert status == "Queued"

    recovered_queue = queue.Queue()
    retry_result = service.recover_queued_ddl_commands(recovered_queue)
    assert retry_result["enqueued_ids"] == ["ddl-1"]


def test_ddl_startup_sweep_runs_before_worker_thread(monkeypatch):
    events = []
    work_queue = queue.Queue()
    monkeypatch.setattr(comicarr, "DDL_QUEUE", work_queue)
    monkeypatch.setattr(comicarr, "DDLPOOL", None)
    monkeypatch.setattr(
        comicarr.helpers,
        "recover_queued_ddl_commands",
        lambda ddl_queue: events.append("recovery"),
        raising=False,
    )
    monkeypatch.setattr(comicarr.helpers, "ddl_downloader", lambda ddl_queue: events.append("worker"))

    comicarr.queue_schedule("ddl_queue", "start")
    comicarr.DDLPOOL.join(timeout=2)

    assert events == ["recovery", "worker"]


def test_ddl_startup_sweep_is_skipped_when_worker_is_alive(monkeypatch):
    work_queue = queue.Queue()
    live_worker = MagicMock()
    live_worker.is_alive.return_value = True
    recover = MagicMock()
    worker = MagicMock()
    monkeypatch.setattr(comicarr, "DDL_QUEUE", work_queue)
    monkeypatch.setattr(comicarr, "DDLPOOL", live_worker)
    monkeypatch.setattr(comicarr.helpers, "recover_queued_ddl_commands", recover, raising=False)
    monkeypatch.setattr(comicarr.helpers, "ddl_downloader", worker)

    comicarr.queue_schedule("ddl_queue", "start")

    recover.assert_not_called()
    worker.assert_not_called()
    assert comicarr.DDLPOOL is live_worker


def test_recovery_preserves_complete_canonical_ddl_command():
    payload = _complete_ddl_payload()
    payload.update({"provider": "DDL", "ddl": True})

    kind, command = recovery._resume_item_from_row(
        {"downloader_type": "ddl", "issueid": "issue-1"},
        payload,
    )

    assert kind == "ddl"
    assert command == _complete_ddl_payload()


def _getcomics_link(site="Main Server", **overrides):
    link = {
        "series": "Saga",
        "year": "2026",
        "size": "10 MB",
        "issues": "1",
        "pack": False,
        "links": "https://downloads.invalid/issue.cbz",
        "site": site,
    }
    link.update(overrides)
    return link


def _getcomics_batch_downloader():
    downloader = getcomics.GC.__new__(getcomics.GC)
    downloader.issueid = "issue-1"
    downloader.comicid = "comic-1"
    downloader.oneoff = False
    return downloader


def test_getcomics_batch_validates_all_items_before_mutation(monkeypatch):
    queue_command = MagicMock()
    monkeypatch.setattr(service, "queue_ddl_download", queue_command)
    downloader = _getcomics_batch_downloader()

    result = downloader._queue_download_batch(
        "ddl-batch",
        "https://getcomics.invalid/saga",
        [_getcomics_link(), _getcomics_link(site="Unsupported Host")],
        "Saga (2026)",
        [{"pack": False, "IssueID": "issue-1"}],
        None,
    )

    assert result["success"] is False
    assert result["validation_error"] is True
    assert result["queued_ids"] == []
    assert result["failed_ids"] == ["ddl-batch-2"]
    queue_command.assert_not_called()


def test_getcomics_batch_reports_partial_handoff_without_total_failure(monkeypatch):
    queue_command = MagicMock(
        side_effect=[
            {"success": True},
            {"success": False, "error": "queue unavailable", "handoff_error": True},
        ]
    )
    monkeypatch.setattr(service, "queue_ddl_download", queue_command)
    downloader = _getcomics_batch_downloader()

    result = downloader._queue_download_batch(
        "ddl-batch",
        "https://getcomics.invalid/saga",
        [_getcomics_link(), _getcomics_link(site="Mega")],
        "Saga (2026)",
        [{"pack": False, "IssueID": "issue-1"}],
        None,
    )

    assert result == {
        "success": True,
        "partial": True,
        "site": "GC-Mega",
        "queued_ids": ["ddl-batch-1"],
        "failed_ids": ["ddl-batch-2"],
    }
    assert "https://" not in repr(result)


def test_worker_marks_poison_item_failed_and_continues_to_shutdown(monkeypatch):
    work = queue.Queue()
    work.put({"id": "ddl-bad", "link": "https://example.invalid", "site": "DDL(GetComics)"})
    work.put("exit")
    statuses = []
    monkeypatch.setattr(comicarr.DDL_LOCK, "locked", lambda: False)
    monkeypatch.setattr(comicarr, "DDL_QUEUED", {"ddl-bad"})
    monkeypatch.setattr(comicarr, "DDL_STUCK_NOTIFIED", {"ddl-bad"})
    monkeypatch.setattr(
        service.db,
        "upsert",
        lambda table, values, controls: statuses.append((table, values, controls)),
    )

    service.ddl_downloader(work)

    assert statuses[-1][1]["status"] == "Failed"
    assert "ddl-bad" not in comicarr.DDL_QUEUED
    assert "ddl-bad" not in comicarr.DDL_STUCK_NOTIFIED
    assert work.empty()


class _TrackingLock:
    def __init__(self):
        self._locked = False
        self.acquires = 0
        self.releases = 0

    def locked(self):
        return self._locked

    def acquire(self):
        assert not self._locked
        self._locked = True
        self.acquires += 1

    def release(self):
        assert self._locked, "attempted to release an unlocked DDL lock"
        self._locked = False
        self.releases += 1


class _Response:
    url = "https://downloads.invalid/Saga.zip"

    def __init__(self, chunks=(b"comic",), content_length="5"):
        self.headers = {"Content-length": content_length}
        self._chunks = chunks

    def iter_content(self, chunk_size):
        return iter(self._chunks)


def _downloader(monkeypatch, tmp_path, *, response=None):
    downloader = getcomics.GC.__new__(getcomics.GC)
    downloader.headers = {}
    downloader.session = MagicMock()
    downloader.session.get.return_value = response or _Response()
    downloader.cookie_receipt = MagicMock()
    lock = _TrackingLock()
    monkeypatch.setattr(comicarr, "DDL_LOCK", lock)
    monkeypatch.setattr(comicarr, "DDL_QUEUED", set())
    monkeypatch.setattr(
        comicarr,
        "CONFIG",
        SimpleNamespace(
            DDL_LOCATION=str(tmp_path),
            ENFORCE_PERMS=False,
            CHMOD_FILE="0660",
            CHMOD_DIR="0777",
        ),
    )
    monkeypatch.setattr(getcomics.db, "upsert", lambda *args, **kwargs: None)
    return downloader, lock


@pytest.mark.parametrize("failure", ["cookie", "directory", "timeout", "download", "missing"])
def test_downloadit_releases_lock_once_on_early_failures(tmp_path, monkeypatch, failure):
    downloader, lock = _downloader(monkeypatch, tmp_path)

    if failure == "cookie":
        downloader.cookie_receipt.side_effect = RuntimeError("cookie failed")
    elif failure == "directory":
        missing = tmp_path / "missing"
        comicarr.CONFIG.DDL_LOCATION = str(missing)
        monkeypatch.setattr(comicarr.filechecker, "validateAndCreateDirectory", lambda *args: False)
    elif failure == "timeout":
        downloader.session.get.side_effect = requests.exceptions.Timeout("timed out")
    elif failure == "download":
        monkeypatch.setattr(getcomics, "write_chunks_atomically", MagicMock(side_effect=OSError("disk full")))
    elif failure == "missing":
        monkeypatch.setattr(getcomics, "write_chunks_atomically", lambda *args, **kwargs: None)

    result = downloader.downloadit(
        "ddl-1",
        "https://downloads.invalid/Saga.zip",
        "https://getcomics.invalid/saga",
        issueid="issue-1",
        remote_filesize=5,
        link_type="GC-Main",
    )

    assert result["success"] is False
    assert lock.locked() is False
    assert (lock.acquires, lock.releases) == (1, 1)


@pytest.mark.parametrize("extraction_succeeds", [False, True])
def test_downloadit_holds_lock_through_zip_publication(tmp_path, monkeypatch, extraction_succeeds):
    downloader, lock = _downloader(monkeypatch, tmp_path)

    def write_archive(destination, chunks):
        destination.write_bytes(b"zip")

    def extract_archive(source, destination):
        assert lock.locked(), "DDL lock must cover extraction and atomic publication"
        if not extraction_succeeds:
            raise OSError("invalid zip")
        destination.mkdir()
        return destination

    monkeypatch.setattr(getcomics, "write_chunks_atomically", write_archive)
    monkeypatch.setattr(getcomics, "extract_zip_atomically", extract_archive)

    result = downloader.downloadit(
        "ddl-1",
        "https://downloads.invalid/Saga.zip",
        "https://getcomics.invalid/saga",
        issueid="issue-1",
        remote_filesize=5,
        link_type="GC-Main",
    )

    assert result["success"] is extraction_succeeds
    assert lock.locked() is False
    assert (lock.acquires, lock.releases) == (1, 1)
