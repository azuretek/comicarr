#  Copyright (C) 2025–2026 Comicarr contributors
#
#  This file is part of Comicarr.
#
#  Comicarr is free software: you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.

from types import SimpleNamespace
from unittest.mock import MagicMock

import comicarr
from comicarr import updater


def _configure_updater(monkeypatch, *, annuals_on, rows, cv_results):
    refresh_thread = MagicMock()
    monkeypatch.setattr(
        comicarr,
        "CONFIG",
        SimpleNamespace(ANNUALS_ON=annuals_on, BACKFILL_TIMESPAN=15),
    )
    monkeypatch.setattr(comicarr, "DB_BACKFILL", False)
    monkeypatch.setattr(comicarr, "UPDATER_STATUS", "Waiting")
    monkeypatch.setattr(comicarr, "REFRESH_QUEUE", SimpleNamespace(queue=[]))
    monkeypatch.setattr(comicarr, "importer", SimpleNamespace(refresh_thread=refresh_thread))
    monkeypatch.setattr(
        comicarr,
        "cv",
        SimpleNamespace(
            getComic=lambda **_kwargs: {
                "count": max(1, len(cv_results)),
                "totalcount": max(1, len(cv_results)),
                "results": cv_results,
            }
        ),
    )
    monkeypatch.setattr(updater.db, "select_one", MagicMock(return_value=None))
    monkeypatch.setattr(updater.db, "select_all", MagicMock(return_value=rows))
    monkeypatch.setattr(updater.db, "upsert", MagicMock())
    monkeypatch.setattr(updater.helpers, "job_management", MagicMock())
    monkeypatch.setattr(updater.helpers, "utctimestamp", MagicMock(return_value="now"))
    return refresh_thread


def test_watchlist_updater_skips_non_comicvine_series_ids(monkeypatch):
    refresh_thread = _configure_updater(
        monkeypatch,
        annuals_on=False,
        cv_results=[
            {
                "comicid": {"id": 123},
                "last_updated": "2026-07-10 08:00:00",
            }
        ],
        rows=[
            {
                "ComicID": "mal-1",
                "ComicName": "Manga Series",
                "Status": "Active",
                "ComicYear": "2026",
                "LastUpdated": "2026-07-01 08:00:00",
                "Total": 10,
            },
            {
                "ComicID": "123",
                "ComicName": "Comic Series",
                "Status": "Active",
                "ComicYear": "2026",
                "LastUpdated": "2026-07-01 08:00:00",
                "Total": 10,
            },
        ],
    )

    updater.watchlist_updater()

    refresh_thread.assert_called_once_with([{"comicid": 123, "comicname": "Comic Series", "seriesyear": "2026"}])


def test_watchlist_updater_keeps_annual_release_lookup_id_as_text(monkeypatch):
    refresh_thread = _configure_updater(
        monkeypatch,
        annuals_on=True,
        cv_results=[],
        rows=[
            {
                "ComicID": "456",
                "ComicName": None,
                "Status": "Active",
                "ComicYear": "2026",
                "LastUpdated": None,
                "Total": 0,
                "ReleaseComicID": None,
            }
        ],
    )

    updater.watchlist_updater()

    refresh_thread.assert_called_once_with([{"comicid": 456, "comicname": None, "seriesyear": "2026"}])
    annual_lookup = updater.db.select_one.call_args.args[0]
    release_id = next(iter(annual_lookup.compile().params.values()))
    assert release_id == "456"
    assert isinstance(release_id, str)
