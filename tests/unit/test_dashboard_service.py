#  Copyright (C) 2025–2026 Comicarr contributors
#
#  This file is part of Comicarr.
#
#  Comicarr is free software: you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.

"""Tests for comicarr.app.dashboard.service."""

from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture(autouse=True)
def _default_queue_count(monkeypatch):
    monkeypatch.setattr("comicarr.app.dashboard.service.dl_queries.count_active_ddl_items", lambda: 0)
    monkeypatch.setattr("comicarr.app.dashboard.service.dl_queries.get_active_ddl_preview", lambda limit: [])


class _FakeDBConnection:
    """Minimal DB stub for testing dashboard queries."""

    def __init__(self, select_results=None, selectone_result=None):
        self._select_results = select_results or {}
        self._selectone_result = selectone_result
        self._select_calls = []
        self._selectone_calls = []

    def select(self, query, args=None):
        self._select_calls.append((query, args))
        for key, val in self._select_results.items():
            if key in query:
                return val
        return []

    def selectone(self, query, args=None):
        self._selectone_calls.append((query, args))
        return self._selectone_result or []


class TestGetDashboardData:
    """Test dashboard data aggregation."""

    @patch("comicarr.app.dashboard.service.db")
    @patch("comicarr.app.dashboard.service.comicarr")
    def test_returns_recently_downloaded(self, mock_comicarr, mock_db):
        mock_comicarr.AI_CLIENT = None
        recent = [
            {
                "ComicName": "Spider-Man",
                "Issue_Number": "1",
                "DateAdded": "2026-04-01",
                "Status": "Snatched",
                "Provider": "nzb",
                "ComicID": "100",
                "IssueID": "200",
                "ComicImage": "http://img/1.jpg",
            },
        ]
        fake_db = _FakeDBConnection(select_results={"snatched": recent})
        mock_db.DBConnection.return_value = fake_db

        from comicarr.app.dashboard.service import get_dashboard_data

        result = get_dashboard_data(None)

        assert len(result["recently_downloaded"]) == 1
        assert result["recently_downloaded"][0]["ComicName"] == "Spider-Man"

    @patch("comicarr.app.dashboard.service.db")
    @patch("comicarr.app.dashboard.service.comicarr")
    def test_recent_activity_uses_an_inclusive_30_day_cutoff(self, mock_comicarr, mock_db, monkeypatch):
        mock_comicarr.AI_CLIENT = None
        cutoff = datetime(2026, 6, 10, 12, 0, 0)
        monkeypatch.setattr("comicarr.app.dashboard.service.recent_activity_cutoff", lambda: cutoff)
        fake_db = _FakeDBConnection(select_results={"snatched": []})
        mock_db.DBConnection.return_value = fake_db

        from comicarr.app.dashboard.service import get_dashboard_data

        get_dashboard_data(None)

        recent_query, args = next((query, args) for query, args in fake_db._select_calls if "FROM snatched" in query)
        assert "WHERE s.DateAdded >= ?" in recent_query
        assert args == ["2026-06-10 12:00:00"]

    @patch("comicarr.app.dashboard.service.db")
    @patch("comicarr.app.dashboard.service.comicarr")
    def test_returns_current_week_library_releases(self, mock_comicarr, mock_db, monkeypatch):
        mock_comicarr.AI_CLIENT = None
        upcoming = [
            {
                "ComicName": "Batman",
                "IssueNumber": "5",
                "IssueDate": "2026-04-06",
                "ComicID": "300",
                "Status": "Wanted",
            },
        ]
        fake_db = _FakeDBConnection(select_results={"snatched": []})
        mock_db.DBConnection.return_value = fake_db
        get_upcoming = MagicMock(return_value=upcoming)
        monkeypatch.setattr("comicarr.app.dashboard.service.storyarcs_service.get_upcoming", get_upcoming)

        from comicarr.app.dashboard.service import get_dashboard_data

        result = get_dashboard_data(None)

        get_upcoming.assert_called_once_with(include_downloaded=True)
        assert len(result["upcoming_releases"]) == 1
        assert result["upcoming_releases"][0]["ComicName"] == "Batman"
        assert all("futureupcoming" not in query for query, _args in fake_db._select_calls)

    @patch("comicarr.app.dashboard.service.db")
    @patch("comicarr.app.dashboard.service.comicarr")
    def test_returns_active_queue_preview_with_shared_queue_query(self, mock_comicarr, mock_db, monkeypatch):
        mock_comicarr.AI_CLIENT = None
        queue_items = [{"ID": "queued-1", "series": "Batman", "status": "Queued"}]
        get_active_preview = MagicMock(return_value=queue_items)
        monkeypatch.setattr("comicarr.app.dashboard.service.dl_queries.get_active_ddl_preview", get_active_preview)
        fake_db = _FakeDBConnection(
            select_results={"snatched": []},
            selectone_result={"total_series": 1, "total_issues": 1, "total_expected": 1},
        )
        mock_db.DBConnection.return_value = fake_db

        from comicarr.app.dashboard.service import get_dashboard_data

        result = get_dashboard_data(None)

        get_active_preview.assert_called_once_with(limit=5)
        assert result["active_queue"] == queue_items

    @patch("comicarr.app.dashboard.service.db")
    @patch("comicarr.app.dashboard.service.comicarr")
    def test_returns_stats(self, mock_comicarr, mock_db):
        mock_comicarr.AI_CLIENT = None
        stats_row = {"total_series": 10, "total_issues": 250, "total_expected": 500}
        fake_db = _FakeDBConnection(
            select_results={"snatched": []},
            selectone_result=stats_row,
        )
        mock_db.DBConnection.return_value = fake_db

        from comicarr.app.dashboard.service import get_dashboard_data

        result = get_dashboard_data(None)

        assert result["stats"]["total_series"] == 10
        assert result["stats"]["total_issues"] == 250
        assert result["stats"]["total_expected"] == 500
        assert result["stats"]["completion_pct"] == 50.0

    @patch("comicarr.app.dashboard.service.db")
    @patch("comicarr.app.dashboard.service.comicarr")
    def test_returns_active_queue_count(self, mock_comicarr, mock_db, monkeypatch):
        mock_comicarr.AI_CLIENT = None
        mock_comicarr.CONFIG.COMIC_DIR = "/comics"
        mock_comicarr.CONFIG.MANGA_DIR = "/manga"
        monkeypatch.setattr(
            "comicarr.app.dashboard.service.dl_queries.count_active_ddl_items",
            lambda: 3,
        )
        fake_db = _FakeDBConnection(
            select_results={"snatched": []},
            selectone_result={"total_series": 1, "total_issues": 1, "total_expected": 1},
        )
        mock_db.DBConnection.return_value = fake_db

        from comicarr.app.dashboard.service import get_dashboard_data

        result = get_dashboard_data(None)

        assert result["stats"]["queue_count"] == 3
        assert result["scan_targets"] == {"comic": True, "manga": True}

    @patch("comicarr.app.dashboard.service.db")
    @patch("comicarr.app.dashboard.service.comicarr")
    def test_queue_count_failure_preserves_other_stats(self, mock_comicarr, mock_db, monkeypatch):
        mock_comicarr.AI_CLIENT = None
        monkeypatch.setattr(
            "comicarr.app.dashboard.service.dl_queries.count_active_ddl_items",
            MagicMock(side_effect=RuntimeError("count failed")),
        )
        fake_db = _FakeDBConnection(
            select_results={"snatched": []},
            selectone_result={"total_series": 1, "total_issues": 1, "total_expected": 1},
        )
        mock_db.DBConnection.return_value = fake_db

        from comicarr.app.dashboard.service import get_dashboard_data

        result = get_dashboard_data(None)

        assert result["stats"]["queue_count"] == 0
        assert result["stats"]["total_series"] == 1
        assert result["stats"]["total_issues"] == 1

    @patch("comicarr.app.dashboard.service.db")
    @patch("comicarr.app.dashboard.service.comicarr")
    def test_returns_ai_activity_when_configured(self, mock_comicarr, mock_db):
        mock_comicarr.AI_CLIENT = MagicMock()
        activity = [
            {
                "timestamp": "2026-04-05T12:00:00",
                "feature_type": "search",
                "action_description": "Expanded search query",
                "prompt_tokens": 100,
                "completion_tokens": 50,
                "success": True,
            },
        ]
        fake_db = _FakeDBConnection(
            select_results={"snatched": [], "ai_activity_log": activity},
        )
        mock_db.DBConnection.return_value = fake_db

        from comicarr.app.dashboard.service import get_dashboard_data

        result = get_dashboard_data(None)

        assert result["ai_configured"] is True
        assert len(result["ai_activity"]) == 1
        assert result["ai_activity"][0]["feature_type"] == "search"

    @patch("comicarr.app.dashboard.service.db")
    @patch("comicarr.app.dashboard.service.comicarr")
    def test_ai_not_configured(self, mock_comicarr, mock_db):
        mock_comicarr.AI_CLIENT = None
        mock_comicarr.CONFIG.AI_BASE_URL = None
        fake_db = _FakeDBConnection(select_results={"snatched": []})
        mock_db.DBConnection.return_value = fake_db

        from comicarr.app.dashboard.service import get_dashboard_data

        result = get_dashboard_data(None)

        assert result["ai_configured"] is False
        assert result["ai_activity"] == []

    @patch("comicarr.app.dashboard.service.db")
    @patch("comicarr.app.dashboard.service.comicarr")
    def test_handles_empty_tables(self, mock_comicarr, mock_db):
        mock_comicarr.AI_CLIENT = None
        mock_comicarr.CONFIG.AI_BASE_URL = None
        fake_db = _FakeDBConnection(
            select_results={"snatched": []},
            selectone_result=[],
        )
        mock_db.DBConnection.return_value = fake_db

        from comicarr.app.dashboard.service import get_dashboard_data

        result = get_dashboard_data(None)

        assert result["recently_downloaded"] == []
        assert result["upcoming_releases"] == []
        assert result["stats"] == {"queue_count": 0}
        assert result["ai_activity"] == []
        assert result["ai_configured"] is False

    @patch("comicarr.app.dashboard.service.db")
    @patch("comicarr.app.dashboard.service.comicarr")
    def test_handles_db_errors_gracefully(self, mock_comicarr, mock_db):
        mock_comicarr.AI_CLIENT = None
        mock_db.DBConnection.side_effect = Exception("DB connection failed")

        from comicarr.app.dashboard.service import get_dashboard_data

        result = get_dashboard_data(None)

        # Should return empty defaults, not raise
        assert result["recently_downloaded"] == []
        assert result["upcoming_releases"] == []
        assert result["stats"] == {"queue_count": 0}

    @patch("comicarr.app.dashboard.service.db")
    @patch("comicarr.app.dashboard.service.comicarr")
    def test_completion_pct_zero_when_no_expected(self, mock_comicarr, mock_db):
        mock_comicarr.AI_CLIENT = None
        stats_row = {"total_series": 0, "total_issues": 0, "total_expected": 0}
        fake_db = _FakeDBConnection(
            select_results={"snatched": []},
            selectone_result=stats_row,
        )
        mock_db.DBConnection.return_value = fake_db

        from comicarr.app.dashboard.service import get_dashboard_data

        result = get_dashboard_data(None)

        assert result["stats"]["completion_pct"] == 0
