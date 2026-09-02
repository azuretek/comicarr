#  Copyright (C) 2026 Comicarr contributors
#
#  This file is part of Comicarr.
#
#  Comicarr is free software: you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.

"""Live-path wiring for manga sync, blended search, and bare-number settings."""

import ast
import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

from comicarr.app.manga.acquisition import search_plan_for_series
from comicarr.app.manga.parse import parse_in_series_context, parse_kwargs_for_series
from comicarr.app.manga.sync import arm_manga_sync_job, next_interval_run
from comicarr.rsscheck import mangaCheck
from comicarr.search import _build_manga_search_terms

_INIT_PATH = Path(__file__).resolve().parents[2] / "comicarr" / "__init__.py"


def test_next_interval_run_fires_now_when_overdue():
    now = 1_700_000_000
    when = next_interval_run(now - 3600, 30, now_ts=now)
    assert when == datetime.datetime.utcfromtimestamp(now)


def test_next_interval_run_waits_out_the_remaining_interval():
    now = 1_700_000_000
    when = next_interval_run(now - 600, 30, now_ts=now)
    assert when == datetime.datetime.utcfromtimestamp(now + 1200)


def test_arm_manga_sync_job_modifies_next_run_unless_paused():
    scheduler = MagicMock()
    when = arm_manga_sync_job(scheduler, "Waiting", None, 60)
    scheduler.modify.assert_called_once_with(next_run_time=when)
    scheduler.reset_mock()
    assert arm_manga_sync_job(scheduler, "Paused", None, 60) is None
    scheduler.modify.assert_not_called()


def test_init_arms_manga_sync_after_pause():
    tree = ast.parse(_INIT_PATH.read_text(encoding="utf-8"))
    source = _INIT_PATH.read_text(encoding="utf-8")
    assert "MANGA_SYNC_SCHEDULER.pause()" in source
    assert "arm_manga_sync_job" in source
    helper_ids = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if isinstance(node.func, ast.Name) and node.func.id == "_add_recurring_job":
            for keyword in node.keywords:
                if keyword.arg == "id" and isinstance(keyword.value, ast.Constant):
                    helper_ids.add(keyword.value.value)
    assert "manga_sync" in helper_ids


def test_blended_plan_skips_chapters_inside_released_volumes():
    series = {"MonitorMode": "blended"}
    issues = [
        {"IssueID": "md-x-ch1", "ChapterNumber": "1", "VolumeNumber": "1", "Status": "Wanted"},
        {"IssueID": "md-x-ch2", "ChapterNumber": "2", "VolumeNumber": "1", "Status": "Wanted"},
        {"IssueID": "md-x-ch100", "ChapterNumber": "100", "VolumeNumber": "2", "Status": "Wanted"},
        {"IssueID": "md-x-ch101", "ChapterNumber": "101", "VolumeNumber": None, "Status": "Wanted"},
    ]
    targets = search_plan_for_series(series, issues)
    kinds = {(item["kind"], str(item.get("number"))) for item in targets}
    assert ("volume", "1") in kinds
    assert ("volume", "2") in kinds
    assert ("chapter", "101") in kinds
    assert ("chapter", "1") not in kinds
    assert ("chapter", "2") not in kinds


def test_volumes_mode_does_not_search_wanted_chapters():
    series = {"MonitorMode": "volumes"}
    issues = [
        {"IssueID": "md-x-ch1", "ChapterNumber": "1", "VolumeNumber": "1", "Status": "Wanted"},
    ]
    targets = search_plan_for_series(series, issues)
    assert targets == [{"kind": "volume", "number": "1"}]


def test_owned_volume_drops_that_volume_from_the_plan():
    series = {"MonitorMode": "blended"}
    issues = [
        {"IssueID": "md-x-v1", "ChapterNumber": None, "VolumeNumber": "1", "Status": "Downloaded"},
        {"IssueID": "md-x-ch2", "ChapterNumber": "20", "VolumeNumber": "2", "Status": "Wanted"},
        {"IssueID": "md-x-ch21", "ChapterNumber": "21", "VolumeNumber": None, "Status": "Wanted"},
    ]
    targets = search_plan_for_series(series, issues)
    assert {"kind": "volume", "number": "1"} not in targets
    assert {"kind": "volume", "number": "2"} in targets
    assert any(item.get("id") == "md-x-ch21" for item in targets)


def test_manga_check_searches_blended_targets_not_every_wanted_chapter():
    series = {
        "ComicID": "md-abc",
        "ComicName": "One Piece",
        "ComicYear": "1999",
        "ComicPublisher": "Shueisha",
        "AlternateSearch": None,
        "UseFuzzy": None,
        "ComicVersion": None,
        "ComicName_Filesafe": "One Piece",
        "MonitorMode": "blended",
    }
    issues = [
        {"IssueID": "md-abc-ch1", "ChapterNumber": "1", "VolumeNumber": "1", "Status": "Wanted"},
        {"IssueID": "md-abc-ch100", "ChapterNumber": "100", "VolumeNumber": None, "Status": "Wanted"},
    ]
    with (
        patch("comicarr.CONFIG", MagicMock(FAILED_DOWNLOAD_HANDLING=False, FAILED_AUTO=False)),
        patch("comicarr.rsscheck.helpers") as mock_helpers,
        patch("comicarr.rsscheck.db") as mock_db,
        patch("comicarr.search.search_init") as mock_search,
    ):
        mock_db.select_all.side_effect = [[series], issues]
        mock_helpers.issue_status.return_value = False
        mangaCheck()

    assert mock_search.call_count == 2
    volume_call = mock_search.call_args_list[0]
    chapter_call = mock_search.call_args_list[1]
    assert volume_call.kwargs["volume_number"] == "1"
    assert volume_call.kwargs.get("chapter_number") in (None, "")
    assert chapter_call.kwargs["chapter_number"] == "100"
    assert chapter_call.kwargs.get("volume_number") in (None, "")
    assert volume_call.kwargs["booktype"] == "manga"


def test_build_manga_search_terms_is_exclusive_volume_or_chapter():
    volume_terms = _build_manga_search_terms("One Piece", None, "10")
    assert volume_terms == ["One Piece v10"]
    chapter_terms = _build_manga_search_terms("One Piece", "1161", "103")
    assert "One Piece c1161" in chapter_terms
    assert "One Piece chapter 1161" in chapter_terms
    assert not any("v103" in term for term in chapter_terms)


def test_parse_in_series_context_uses_persisted_volumes_mode():
    result = parse_in_series_context(
        "Naruto 12.cbr",
        series={"BareNumberMode": "volumes"},
        filenames=["Naruto 12.cbr", "Naruto 13.cbr"],
    )
    assert result["volume_number"] == 12
    assert result["chapter_number"] is None


def test_parse_kwargs_auto_passes_folder_bare_numbers():
    kwargs = parse_kwargs_for_series(
        {"BareNumberMode": "auto"},
        ["Naruto 1.cbr", "Naruto 2.cbr", "Naruto v10.cbz"],
        volume_count=72,
        chapter_count=700,
    )
    assert kwargs["bare_number_mode"] == "auto"
    assert kwargs["bare_numbers"] == ["1", "2"]
    assert kwargs["volume_count"] == 72


def test_folder_scan_numbers_a_watchlisted_manga_series_by_volume():
    """The folder scan must ask whether a series is numbered by volume.

    Deriving the number inline meant a manga series fell through to the issue
    branch, so a volume file yielded no number and matched no issue.
    """
    pp_path = Path(__file__).resolve().parents[2] / "comicarr" / "postprocessor.py"
    tree = ast.parse(pp_path.read_text(encoding="utf-8"))

    called = {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    assert "volume_identifies_file" in called, "the folder scan no longer consults the volume predicate"
    assert "numbered_by_volume" in called, "the scan's issue-number checks no longer consult the exemption"
    # the year gate must actually be reached, and must be reached through the
    # composed helper -- not handed a flag the scan computed for another purpose
    assert "volume_settles_year_for_match" in called, "the scan no longer consults the volume year gate"
    assert "chapter_named_file" in called, (
        "the scan no longer distinguishes a chapter file from a volume file, so a "
        "defaulted v1 will locate c181 as issue 1 again"
    )
    assert "manga_volume_rows" in called, (
        "the scan no longer resolves a manga volume on VolumeNumber, so v20 will "
        "attach to chapter 20 on MangaDex again"
    )
    assert "volume_match_settles_year" in called, "the volume year gate is defined but never called"

    settles_year_args = [
        node.args
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "volume_match_settles_year"
    ]
    assert settles_year_args, "volume_match_settles_year is never called"
    for args in settles_year_args:
        names = {arg.id for arg in args if isinstance(arg, ast.Name)}
        assert "lonevol" not in names, (
            "the year gate is keyed off lonevol again -- manga has no ComicVersion, "
            "so that defaults to 1 and only v01 would pass"
        )

    watch_value_keys = [
        key.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Dict)
        for key in node.keys
        if isinstance(key, ast.Constant) and isinstance(key.value, str)
    ]
    assert watch_value_keys.count("IsManga") == watch_value_keys.count("IsArc"), (
        "every WatchValues row must carry the manga signal, not just the watchlist one"
    )


def test_the_volume_numbered_type_list_has_a_single_owner():
    """The scan tested a hardcoded TPB/GN/HC/One-Shot list in eight places.

    Each copy silently omitted manga, so a manga volume file failed a different
    check depending on which copy it reached. The list now lives in one tuple.

    Asserted over the AST rather than the raw source: a source-text count is
    blind to a duplicate written with single quotes, and fails on a mere
    mention of TPB in a comment or docstring.
    """
    pp_path = Path(__file__).resolve().parents[2] / "comicarr" / "postprocessor.py"
    tree = ast.parse(pp_path.read_text(encoding="utf-8"))

    definitions = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == "_COLLECTED_TYPES" for target in node.targets)
    ]
    assert len(definitions) == 1, "_COLLECTED_TYPES must be defined exactly once"

    value = definitions[0].value
    assert isinstance(value, ast.Tuple), "_COLLECTED_TYPES must stay a literal tuple"
    assert [element.value for element in value.elts] == ["TPB", "HC", "GN"]

    # and no other literal "TPB" may exist -- quote style is irrelevant to the
    # AST, and a comment or docstring mentioning TPB is not a Constant of it
    literals = [
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and node.value == "TPB"
    ]
    assert len(literals) == 1, "the volume-numbered type list has been duplicated again"
