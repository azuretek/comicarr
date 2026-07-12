#  Copyright (C) 2025–2026 Comicarr contributors
#
#  This file is part of Comicarr.
#
#  Comicarr is free software: you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.

"""Tests for dashboard orchestration around Core query helpers."""

from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from comicarr.app.dashboard import service


@pytest.fixture(autouse=True)
def _dashboard_dependencies(monkeypatch):
    """Keep service tests focused on payload/default behavior, not database transport."""
    runtime = SimpleNamespace(
        AI_CLIENT=None,
        CONFIG=SimpleNamespace(AI_BASE_URL=None, COMIC_DIR=None, MANGA_DIR=None),
    )
    monkeypatch.setattr(service, "comicarr", runtime)
    monkeypatch.setattr(service.dashboard_queries, "get_recent_activity", lambda cutoff: [])
    monkeypatch.setattr(service.dashboard_queries, "get_library_stats", lambda content_type=None: None)
    monkeypatch.setattr(service.dashboard_queries, "get_recent_ai_activity", lambda: [])
    monkeypatch.setattr(service.dl_queries, "count_active_ddl_items", lambda: 0)
    monkeypatch.setattr(service.dl_queries, "get_active_ddl_preview", lambda limit: [])
    monkeypatch.setattr(service.storyarcs_service, "get_upcoming", lambda include_downloaded: [])


class TestGetDashboardData:
    """Test dashboard aggregation and error defaults."""

    def test_returns_recently_downloaded(self, monkeypatch):
        recent = [{"ComicName": "Spider-Man", "Issue_Number": "1", "IssueID": "200"}]
        monkeypatch.setattr(service.dashboard_queries, "get_recent_activity", lambda cutoff: recent)

        result = service.get_dashboard_data(None)

        assert result["recently_downloaded"] == recent

    def test_recent_activity_uses_an_inclusive_30_day_cutoff(self, monkeypatch):
        cutoff = datetime(2026, 6, 10, 12, 0, 0)
        seen = []
        monkeypatch.setattr(service, "recent_activity_cutoff", lambda: cutoff)
        monkeypatch.setattr(service.dashboard_queries, "get_recent_activity", seen.append)

        service.get_dashboard_data(None)

        assert seen == ["2026-06-10 12:00:00"]

    def test_returns_current_week_library_releases(self, monkeypatch):
        upcoming = [{"ComicName": "Batman", "IssueNumber": "5", "Status": "Wanted"}]
        get_upcoming = MagicMock(return_value=upcoming)
        monkeypatch.setattr(service.storyarcs_service, "get_upcoming", get_upcoming)

        result = service.get_dashboard_data(None)

        get_upcoming.assert_called_once_with(include_downloaded=True)
        assert result["upcoming_releases"] == upcoming

    def test_returns_active_queue_projection(self, monkeypatch):
        queue_items = [{"ID": "queued-1", "series": "Batman", "status": "Queued"}]
        get_active_preview = MagicMock(return_value=queue_items)
        monkeypatch.setattr(service.dl_queries, "get_active_ddl_preview", get_active_preview)

        result = service.get_dashboard_data(None)

        get_active_preview.assert_called_once_with(limit=5)
        assert result["active_queue"] == queue_items

    def test_returns_combined_and_content_type_stats(self, monkeypatch):
        stats = {
            None: {"total_series": 10, "total_issues": 250, "total_expected": 500},
            "manga": {"manga_series": 2, "manga_have": 10, "manga_total": 20},
            "comic": {"comic_series": 8, "comic_have": 240, "comic_total": 480},
        }
        monkeypatch.setattr(
            service.dashboard_queries, "get_library_stats", lambda content_type=None: stats[content_type]
        )

        result = service.get_dashboard_data(None)

        assert result["stats"] == {
            "total_series": 10,
            "total_issues": 250,
            "total_expected": 500,
            "completion_pct": 50.0,
            "queue_count": 0,
            "manga_series": 2,
            "manga_have": 10,
            "manga_total": 20,
            "manga_completion_pct": 50.0,
            "comic_series": 8,
            "comic_have": 240,
            "comic_total": 480,
        }

    def test_returns_active_queue_count_and_scan_targets(self, monkeypatch):
        service.comicarr.CONFIG.COMIC_DIR = "/comics"
        service.comicarr.CONFIG.MANGA_DIR = "/manga"
        monkeypatch.setattr(service.dl_queries, "count_active_ddl_items", lambda: 3)

        result = service.get_dashboard_data(None)

        assert result["stats"]["queue_count"] == 3
        assert result["scan_targets"] == {"comic": True, "manga": True}

    def test_queue_count_failure_preserves_other_stats(self, monkeypatch):
        monkeypatch.setattr(
            service.dashboard_queries,
            "get_library_stats",
            lambda content_type=None: (
                {"total_series": 1, "total_issues": 1, "total_expected": 1} if content_type is None else None
            ),
        )
        monkeypatch.setattr(
            service.dl_queries, "count_active_ddl_items", MagicMock(side_effect=RuntimeError("count failed"))
        )

        result = service.get_dashboard_data(None)

        assert result["stats"]["queue_count"] == 0
        assert result["stats"]["total_series"] == 1

    def test_returns_ai_activity_when_configured(self, monkeypatch):
        service.comicarr.AI_CLIENT = MagicMock()
        activity = [{"feature_type": "search", "success": True}]
        monkeypatch.setattr(service.dashboard_queries, "get_recent_ai_activity", lambda: activity)

        result = service.get_dashboard_data(None)

        assert result["ai_configured"] is True
        assert result["ai_activity"] == activity

    def test_ai_not_configured_keeps_empty_activity(self):
        result = service.get_dashboard_data(None)

        assert result["ai_configured"] is False
        assert result["ai_activity"] == []

    def test_handles_query_errors_gracefully(self, monkeypatch):
        monkeypatch.setattr(
            service.dashboard_queries,
            "get_recent_activity",
            MagicMock(side_effect=RuntimeError("connection failed")),
        )
        monkeypatch.setattr(
            service.dashboard_queries,
            "get_library_stats",
            MagicMock(side_effect=RuntimeError("connection failed")),
        )

        result = service.get_dashboard_data(None)

        assert result["recently_downloaded"] == []
        assert result["upcoming_releases"] == []
        assert result["stats"] == {"queue_count": 0}

    def test_completion_percentage_is_zero_when_no_expected_issues(self, monkeypatch):
        monkeypatch.setattr(
            service.dashboard_queries,
            "get_library_stats",
            lambda content_type=None: (
                {"total_series": 0, "total_issues": 0, "total_expected": 0} if content_type is None else None
            ),
        )

        result = service.get_dashboard_data(None)

        assert result["stats"]["completion_pct"] == 0
