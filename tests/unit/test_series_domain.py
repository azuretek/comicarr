#  Copyright (C) 2025–2026 Comicarr contributors
#
#  This file is part of Comicarr.
#
#  Comicarr is free software: you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.

"""Tests for the series domain service."""

import os
import queue
from types import SimpleNamespace
from unittest.mock import MagicMock, call, patch

import pytest

import comicarr
from comicarr.app.core.context import AppContext
from comicarr.app.search import commands as search_commands
from comicarr.app.series import queries as series_queries
from comicarr.app.series import service as series_service


def _make_ctx(**config_overrides):
    config_values = {
        "COMIC_DIR": None,
        "MANGA_DIR": None,
        "DESTINATION_DIR": None,
        "MANGA_DESTINATION_DIR": None,
        "MULTIPLE_DEST_DIRS": None,
        "NEWCOM_DIR": None,
    }
    config_values.update(config_overrides)
    return AppContext(config=SimpleNamespace(**config_values))


def _comic(location):
    return {
        "ComicName": "Example Series",
        "ComicYear": "2026",
        "ComicLocation": str(location),
    }


def _delete(ctx, location, delete_side_effect=None):
    with (
        patch.object(series_service.series_queries, "get_comic_for_delete", return_value=_comic(location)),
        patch.object(series_service.series_queries, "delete_comic") as delete_from_db,
    ):
        delete_from_db.side_effect = delete_side_effect
        result = series_service.delete_comic(ctx, "123", delete_directory=True)
    return result, delete_from_db


def test_refresh_comic_includes_canonical_series_year(monkeypatch):
    refresh_thread = MagicMock()
    monkeypatch.setattr(comicarr, "REFRESH_QUEUE", SimpleNamespace(queue=[]))
    monkeypatch.setattr(comicarr, "importer", SimpleNamespace(refresh_thread=refresh_thread))
    monkeypatch.setattr(
        series_service.series_queries,
        "get_comic_for_refresh",
        lambda _comic_id: {"ComicName": "Absolute Batman", "ComicYear": "2024"},
    )

    result = series_service.refresh_comic(_make_ctx(), "160294")

    assert result["success"] is True
    refresh_thread.assert_called_once_with(
        [{"comicid": "160294", "comicname": "Absolute Batman", "seriesyear": "2024"}]
    )


def test_refresh_comic_coalesces_existing_mapping_command(monkeypatch):
    refresh_thread = MagicMock()
    refresh_queue = queue.Queue()
    refresh_queue.put({"comicid": "160294", "comicname": "Absolute Batman", "seriesyear": "2024"})
    monkeypatch.setattr(comicarr, "REFRESH_QUEUE", refresh_queue)
    monkeypatch.setattr(comicarr, "importer", SimpleNamespace(refresh_thread=refresh_thread))
    monkeypatch.setattr(
        series_service.series_queries,
        "get_comic_for_refresh",
        lambda _comic_id: {"ComicName": "Absolute Batman", "ComicYear": "2024"},
    )

    result = series_service.refresh_comic(_make_ctx(), "160294")

    assert result == {"success": True, "message": "Already queued for refresh"}
    refresh_thread.assert_not_called()


def test_queue_issue_persists_search_before_async_handoff(monkeypatch):
    mark_wanted = MagicMock()
    enqueue = MagicMock(return_value=SimpleNamespace(run_id="search-run"))
    monkeypatch.setattr(series_service.series_queries, "queue_issue", mark_wanted)
    monkeypatch.setattr(search_commands, "enqueue_search_command", enqueue)

    result = series_service.queue_issue(_make_ctx(), "issue-1", audit_identity="frankie")

    mark_wanted.assert_called_once_with("issue-1", "frankie")
    enqueue.assert_called_once_with({"issueid": "issue-1"}, trigger="issue_wanted")
    assert result == {"success": True, "run_id": "search-run"}


def test_explicit_issue_actions_dual_write_canonical_intent(monkeypatch):
    upsert = MagicMock()
    monkeypatch.setattr(series_queries.db, "upsert", upsert)

    series_queries.queue_issue("issue-1", "frankie")
    series_queries.unqueue_issue("issue-2", "frankie")

    assert upsert.call_args_list == [
        call(
            "issues",
            {"AcquisitionIntent": "wanted", "Status": "Wanted"},
            {"IssueID": "issue-1"},
        ),
        call(
            "issues",
            {"AcquisitionIntent": "skipped", "Status": "Skipped"},
            {"IssueID": "issue-2"},
        ),
    ]


class TestDeleteComicDirectory:
    def test_rejects_directory_when_no_library_root_is_configured(self, tmp_path):
        series_directory = tmp_path / "series"
        series_directory.mkdir()

        result, delete_from_db = _delete(_make_ctx(), series_directory)

        assert result["success"] is False
        assert series_directory.is_dir()
        delete_from_db.assert_not_called()

    def test_rejects_directory_outside_configured_library_roots(self, tmp_path):
        library_root = tmp_path / "library"
        outside_series = tmp_path / "outside" / "series"
        library_root.mkdir()
        outside_series.mkdir(parents=True)

        result, delete_from_db = _delete(
            _make_ctx(DESTINATION_DIR=str(library_root)),
            outside_series,
        )

        assert result["success"] is False
        assert outside_series.is_dir()
        delete_from_db.assert_not_called()

    def test_rejects_path_prefix_sibling_of_library_root(self, tmp_path):
        """A path that shares a string prefix with the root must not authorize deletion."""
        library_root = tmp_path / "library"
        evil_series = tmp_path / "library-evil" / "series"
        library_root.mkdir()
        evil_series.mkdir(parents=True)

        result, delete_from_db = _delete(
            _make_ctx(DESTINATION_DIR=str(library_root)),
            evil_series,
        )

        assert result["success"] is False
        assert evil_series.is_dir()
        delete_from_db.assert_not_called()

    @pytest.mark.parametrize(
        "root_value",
        ["None", "none", "  ", 42],
    )
    def test_rejects_when_configured_roots_are_empty_or_invalid(self, tmp_path, root_value):
        series_directory = tmp_path / "series"
        series_directory.mkdir()

        result, delete_from_db = _delete(
            _make_ctx(DESTINATION_DIR=root_value),
            series_directory,
        )

        assert result["success"] is False
        assert series_directory.is_dir()
        delete_from_db.assert_not_called()

    def test_rejects_configured_library_root_itself(self, tmp_path):
        library_root = tmp_path / "library"
        library_root.mkdir()

        result, delete_from_db = _delete(
            _make_ctx(DESTINATION_DIR=str(library_root)),
            library_root,
        )

        assert result["success"] is False
        assert library_root.is_dir()
        delete_from_db.assert_not_called()

    def test_rejects_symlink_that_escapes_library_root(self, tmp_path):
        library_root = tmp_path / "library"
        outside_series = tmp_path / "outside" / "series"
        library_root.mkdir()
        outside_series.mkdir(parents=True)
        linked_series = library_root / "linked-series"
        linked_series.symlink_to(outside_series, target_is_directory=True)

        result, delete_from_db = _delete(
            _make_ctx(DESTINATION_DIR=str(library_root)),
            linked_series,
        )

        assert result["success"] is False
        assert linked_series.is_symlink()
        assert outside_series.is_dir()
        delete_from_db.assert_not_called()

    def test_unlinks_in_library_symlink_without_removing_target(self, tmp_path):
        library_root = tmp_path / "library"
        real_series = library_root / "real-series"
        real_series.mkdir(parents=True)
        (real_series / "issue.cbz").write_text("x")
        linked_series = library_root / "linked-series"
        linked_series.symlink_to(real_series, target_is_directory=True)

        result, delete_from_db = _delete(
            _make_ctx(DESTINATION_DIR=str(library_root)),
            linked_series,
        )

        assert result["success"] is True
        assert not linked_series.exists()
        assert real_series.is_dir()
        assert (real_series / "issue.cbz").is_file()
        delete_from_db.assert_called_once_with("123")

    def test_unlinks_regular_file_comic_location(self, tmp_path):
        library_root = tmp_path / "library"
        library_root.mkdir()
        series_file = library_root / "series.cbz"
        series_file.write_text("comic-data")

        result, delete_from_db = _delete(
            _make_ctx(DESTINATION_DIR=str(library_root)),
            series_file,
        )

        assert result["success"] is True
        assert not series_file.exists()
        delete_from_db.assert_called_once_with("123")

    def test_rejects_filesystem_root_as_configured_library_root(self, tmp_path):
        series_directory = tmp_path / "series"
        series_directory.mkdir()

        result, delete_from_db = _delete(
            _make_ctx(DESTINATION_DIR=os.sep),
            series_directory,
        )

        assert result["success"] is False
        assert series_directory.is_dir()
        delete_from_db.assert_not_called()

    def test_filesystem_failure_does_not_delete_database_rows(self, tmp_path):
        library_root = tmp_path / "library"
        series_directory = library_root / "series"
        series_directory.mkdir(parents=True)

        with (
            patch.object(
                series_service.series_queries,
                "get_comic_for_delete",
                return_value=_comic(series_directory),
            ),
            patch.object(series_service.shutil, "rmtree", side_effect=OSError("permission denied")),
            patch.object(series_service.series_queries, "delete_comic") as delete_from_db,
        ):
            result = series_service.delete_comic(
                _make_ctx(DESTINATION_DIR=str(library_root)),
                "123",
                delete_directory=True,
            )

        assert result["success"] is False
        assert series_directory.is_dir()
        delete_from_db.assert_not_called()

    @pytest.mark.parametrize(
        "root_key",
        [
            "DESTINATION_DIR",
            "MANGA_DESTINATION_DIR",
            "COMIC_DIR",
            "MANGA_DIR",
            "MULTIPLE_DEST_DIRS",
            "NEWCOM_DIR",
        ],
    )
    def test_valid_strict_descendant_is_removed_before_database_rows(self, tmp_path, root_key):
        library_root = tmp_path / "library"
        series_directory = library_root / "series"
        series_directory.mkdir(parents=True)

        def assert_directory_was_removed(_comic_id):
            assert not series_directory.exists()

        result, delete_from_db = _delete(
            _make_ctx(**{root_key: str(library_root)}),
            series_directory,
            delete_side_effect=assert_directory_was_removed,
        )

        assert result["success"] is True
        assert not series_directory.exists()
        delete_from_db.assert_called_once_with("123")

    def test_missing_valid_directory_still_deletes_database_rows(self, tmp_path):
        library_root = tmp_path / "library"
        missing_series = library_root / "missing-series"
        library_root.mkdir()

        result, delete_from_db = _delete(
            _make_ctx(DESTINATION_DIR=str(library_root)),
            missing_series,
        )

        assert result["success"] is True
        delete_from_db.assert_called_once_with("123")

    def test_database_only_deletion_does_not_validate_or_remove_directory(self, tmp_path):
        outside_series = tmp_path / "outside" / "series"
        outside_series.mkdir(parents=True)
        ctx = _make_ctx()

        with (
            patch.object(
                series_service.series_queries,
                "get_comic_for_delete",
                return_value=_comic(outside_series),
            ),
            patch.object(series_service.series_queries, "delete_comic") as delete_from_db,
        ):
            result = series_service.delete_comic(ctx, "123", delete_directory=False)

        assert result["success"] is True
        assert outside_series.is_dir()
        delete_from_db.assert_called_once_with("123")
