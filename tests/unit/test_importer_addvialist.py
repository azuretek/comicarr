#  Copyright (C) 2025-2026 Comicarr contributors
#
#  This file is part of Comicarr.
#
#  Comicarr is free software: you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.

"""
Tests for comicarr.importer.addvialist — mass-add queue handling.
"""

import queue
from unittest.mock import MagicMock, patch

import comicarr
from comicarr import importer
from comicarr.app.core import runtime
from comicarr.app.core.context import AppContext
from comicarr.importer import addvialist


def _run_single_item(series_queue, issue_queue, item):
    """Process one queue item then exit the addvialist loop."""
    series_queue.put(item)
    series_queue.put("exit")

    with patch("comicarr.importer.addComictoDB") as mock_add:
        with patch("comicarr.importer.time.sleep"):
            with patch.object(comicarr, "ADD_LIST", queue.Queue()):
                addvialist(series_queue, issue_queue)

    return mock_add


class TestAddvialistSeriesyear:
    def test_comicid_only_without_seriesyear(self):
        series_queue = queue.Queue()
        issue_queue = queue.Queue()
        item = {"comicid": "12345", "comicname": None}

        mock_add = _run_single_item(series_queue, issue_queue, item)

        mock_add.assert_called_once_with("12345")

    def test_comicname_without_seriesyear_key(self):
        series_queue = queue.Queue()
        issue_queue = queue.Queue()
        item = {"comicid": "12345", "comicname": "Spider-Man"}

        mock_add = _run_single_item(series_queue, issue_queue, item)

        mock_add.assert_called_once_with("12345")

    def test_comicname_with_seriesyear(self):
        """In-flight mass-add no longer writes GLOBAL_MESSAGES (#484); seriesyear is passed through."""
        series_queue = queue.Queue()
        issue_queue = queue.Queue()
        item = {"comicid": "12345", "comicname": "Spider-Man", "seriesyear": "2020"}

        mock_add = _run_single_item(series_queue, issue_queue, item)

        mock_add.assert_called_once_with("12345")
        assert item["seriesyear"] == "2020"


class TestAddComicPayloads:
    def test_search_service_includes_seriesyear(self):
        from unittest.mock import MagicMock, patch

        from comicarr.app.search.service import add_comic

        ctx = MagicMock()
        with patch("comicarr.importer.importer_thread") as mock_thread:
            result = add_comic(ctx, "4050-99999")

        assert result["success"] is True
        mock_thread.assert_called_once_with([{"comicid": "4050-99999", "comicname": None, "seriesyear": None}])

    def test_series_service_includes_seriesyear(self):
        from unittest.mock import MagicMock, patch

        from comicarr.app.series.service import add_comic

        ctx = MagicMock()
        with patch("comicarr.importer.importer_thread") as mock_thread:
            result = add_comic(ctx, "4050-12345")

        assert result["success"] is True
        mock_thread.assert_called_once_with([{"comicid": "12345", "comicname": None, "seriesyear": None}])


def test_importer_thread_projects_mass_add_pool_to_canonical_runtime(monkeypatch):
    """The DB-writing MASS_ADD thread must share the lifecycle-owned pool reference."""
    ctx = AppContext()
    pool = MagicMock(name="mass_add_pool")
    monkeypatch.setattr(runtime, "_runtime", ctx)
    monkeypatch.setattr(comicarr, "MASS_ADD", None)
    monkeypatch.setattr(importer.threading, "Thread", MagicMock(return_value=pool))

    importer.importer_thread([{"comicid": "12345", "comicname": None}])

    assert ctx.mass_add_pool is pool
    assert comicarr.MASS_ADD is pool
    assert ctx.add_list.get_nowait() == {"comicid": "12345", "comicname": None}
    pool.start.assert_called_once()


def test_refresh_worker_projects_pool_to_canonical_runtime(monkeypatch):
    """The on-demand refresh worker must share the lifecycle-owned pool and queue."""
    ctx = AppContext()
    pool = MagicMock(name="mass_refresh_pool")
    thread = MagicMock(return_value=pool)
    monkeypatch.setattr(runtime, "_runtime", ctx)
    monkeypatch.setattr(comicarr, "MASS_REFRESH", None)
    monkeypatch.setattr(importer.threading, "Thread", thread)

    assert importer._start_refresh_worker() is True

    assert ctx.mass_refresh_pool is pool
    assert comicarr.MASS_REFRESH is pool
    thread.assert_called_once_with(target=importer.updater.addvialist, args=(ctx.refresh_queue,), name="mass-refresh")
    pool.start.assert_called_once()

    monkeypatch.setattr(importer.threading, "current_thread", lambda: pool)
    assert importer.refresh_worker_should_retire(ctx.refresh_queue) is True
    assert ctx.mass_refresh_pool is None
    assert comicarr.MASS_REFRESH is None
