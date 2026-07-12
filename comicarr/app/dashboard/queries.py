#  Copyright (C) 2025–2026 Comicarr contributors
#
#  This file is part of Comicarr.
#
#  Comicarr is free software: you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.

"""SQLAlchemy Core projections owned by the dashboard domain."""

from sqlalchemy import func, or_, select

from comicarr import db
from comicarr.tables import ai_activity_log as t_ai_activity_log
from comicarr.tables import comics as t_comics
from comicarr.tables import snatched as t_snatched


def get_recent_activity(cutoff, limit=10):
    """Return the bounded, newest-first snatch preview at an inclusive cutoff."""
    stmt = (
        select(
            t_snatched.c.ComicName,
            t_snatched.c.Issue_Number,
            t_snatched.c.DateAdded,
            t_snatched.c.Status,
            t_snatched.c.Provider,
            t_snatched.c.ComicID,
            t_snatched.c.IssueID,
            t_comics.c.ComicImage,
        )
        .select_from(t_snatched.outerjoin(t_comics, t_snatched.c.ComicID == t_comics.c.ComicID))
        .where(t_snatched.c.DateAdded >= cutoff)
        .order_by(t_snatched.c.DateAdded.desc())
        .limit(int(limit))
    )
    return db.select_all(stmt)


def get_library_stats(content_type=None):
    """Return combined, manga-only, or comic-only library aggregates."""
    if content_type == "manga":
        columns = (
            func.count().label("manga_series"),
            func.coalesce(func.sum(t_comics.c.Have), 0).label("manga_have"),
            func.coalesce(func.sum(t_comics.c.Total), 0).label("manga_total"),
        )
        conditions = (t_comics.c.Status != "Paused", t_comics.c.ContentType == "manga")
    elif content_type == "comic":
        columns = (
            func.count().label("comic_series"),
            func.coalesce(func.sum(t_comics.c.Have), 0).label("comic_have"),
            func.coalesce(func.sum(t_comics.c.Total), 0).label("comic_total"),
        )
        conditions = (
            t_comics.c.Status != "Paused",
            or_(t_comics.c.ContentType.is_(None), t_comics.c.ContentType == "comic"),
        )
    else:
        columns = (
            func.count().label("total_series"),
            func.coalesce(func.sum(t_comics.c.Have), 0).label("total_issues"),
            func.coalesce(func.sum(t_comics.c.Total), 0).label("total_expected"),
        )
        conditions = (t_comics.c.Status != "Paused",)

    return db.select_one(select(*columns).select_from(t_comics).where(*conditions))


def get_recent_ai_activity(limit=5):
    """Return the dashboard's compact newest-first AI activity preview."""
    stmt = (
        select(
            t_ai_activity_log.c.timestamp,
            t_ai_activity_log.c.feature_type,
            t_ai_activity_log.c.action_description,
            t_ai_activity_log.c.prompt_tokens,
            t_ai_activity_log.c.completion_tokens,
            t_ai_activity_log.c.success,
        )
        .order_by(t_ai_activity_log.c.timestamp.desc())
        .limit(int(limit))
    )
    return db.select_all(stmt)
