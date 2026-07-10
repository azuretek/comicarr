#  Copyright (C) 2025-2026 Comicarr contributors
#
#  This file is part of Comicarr.
#
#  Comicarr is free software: you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.

"""Tests for the current-week industry releases endpoint."""

from types import SimpleNamespace

import pytest
from sqlalchemy import insert

import comicarr
from comicarr import db
from comicarr.app.storyarcs import service as storyarcs_service
from comicarr.app.weekly import router
from comicarr.tables import metadata, weekly


@pytest.fixture
def weekly_db(tmp_path, monkeypatch):
    monkeypatch.setattr(comicarr, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(comicarr, "CONFIG", SimpleNamespace())
    monkeypatch.delenv("DATABASE_URL", raising=False)
    db.shutdown_engine()
    engine = db.get_engine()
    metadata.create_all(engine)
    yield engine
    db.shutdown_engine()


def test_current_week_uses_the_sunday_based_year_at_new_year_boundary():
    """Week zero resolves to the previous Sunday, as My Releases already does."""
    week, year = storyarcs_service.get_current_week(today=__import__("datetime").date(2021, 1, 1))

    assert (week, year) == ("52", "2020")


def test_weekly_endpoint_filters_retained_rows_to_current_week(monkeypatch, weekly_db):
    with weekly_db.begin() as conn:
        conn.execute(
            insert(weekly),
            [
                {
                    "COMIC": "Current title",
                    "ISSUE": "1",
                    "ComicID": "current",
                    "IssueID": "current-1",
                    "weeknumber": "27",
                    "year": "2026",
                },
                {
                    "COMIC": "Retained old title",
                    "ISSUE": "1",
                    "ComicID": "old",
                    "IssueID": "old-1",
                    "weeknumber": "26",
                    "year": "2026",
                },
            ],
        )

    monkeypatch.setattr(router.storyarcs_service, "get_current_week", lambda: ("27", "2026"))

    result = router.get_weekly(ctx=None)

    assert [row["COMIC"] for row in result] == ["Current title"]


def test_weekly_endpoint_matches_unpadded_early_year_week_rows(monkeypatch, weekly_db):
    with weekly_db.begin() as conn:
        conn.execute(
            insert(weekly),
            [
                {
                    "COMIC": "Week one title",
                    "ISSUE": "1",
                    "ComicID": "week-one",
                    "IssueID": "week-one-1",
                    "weeknumber": "1",
                    "year": "2026",
                },
                {
                    "COMIC": "Week two title",
                    "ISSUE": "1",
                    "ComicID": "week-two",
                    "IssueID": "week-two-1",
                    "weeknumber": "2",
                    "year": "2026",
                },
            ],
        )

    monkeypatch.setattr(router.storyarcs_service, "get_current_week", lambda: ("01", "2026"))

    result = router.get_weekly(ctx=None)

    assert [row["COMIC"] for row in result] == ["Week one title"]
