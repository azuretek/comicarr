#  Copyright (C) 2025–2026 Comicarr contributors
#
#  This file is part of Comicarr.
#
#  Comicarr is free software: you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.

"""
Dashboard domain service — aggregates data from existing tables for
the home dashboard view.
"""

from datetime import datetime, timedelta

import comicarr
from comicarr import db, logger
from comicarr.app.downloads import queries as dl_queries
from comicarr.app.storyarcs import service as storyarcs_service

RECENT_ACTIVITY_DAYS = 30


def recent_activity_cutoff(now=None):
    """Return the inclusive cutoff for the dashboard's bounded activity preview."""
    return (now or datetime.now()) - timedelta(days=RECENT_ACTIVITY_DAYS)


def get_dashboard_data(ctx):
    """Aggregate dashboard data from existing tables.

    Returns a dict with recently_downloaded, upcoming_releases, stats,
    ai_activity, and ai_configured flag.
    """
    result = {
        "recently_downloaded": [],
        "active_queue": [],
        "upcoming_releases": [],
        "stats": {"queue_count": 0},
        "ai_activity": [],
        "ai_configured": False,
        "scan_targets": {
            "comic": isinstance(getattr(comicarr.CONFIG, "COMIC_DIR", None), str) and bool(comicarr.CONFIG.COMIC_DIR),
            "manga": isinstance(getattr(comicarr.CONFIG, "MANGA_DIR", None), str) and bool(comicarr.CONFIG.MANGA_DIR),
        },
    }

    # Recent activity is a bounded preview. Full history retains all rows.
    try:
        cutoff = recent_activity_cutoff().strftime("%Y-%m-%d %H:%M:%S")
        recent = db.DBConnection().select(
            "SELECT s.ComicName, s.Issue_Number, s.DateAdded, s.Status, s.Provider, "
            "s.ComicID, s.IssueID, c.ComicImage "
            "FROM snatched s LEFT JOIN comics c ON s.ComicID = c.ComicID "
            "WHERE s.DateAdded >= ? ORDER BY s.DateAdded DESC LIMIT 10",
            [cutoff],
        )
        result["recently_downloaded"] = recent or []
    except Exception as e:
        logger.error("[DASHBOARD] Error fetching recent downloads: %s" % e)

    # Library releases: matching titles from this application current week.
    try:
        result["upcoming_releases"] = storyarcs_service.get_upcoming(include_downloaded=True) or []
    except Exception as e:
        logger.error("[DASHBOARD] Error fetching upcoming: %s" % e)

    # Stats: aggregate from comics (combined + per content type)
    try:
        stats = db.DBConnection().selectone(
            "SELECT COUNT(*) as total_series, "
            "COALESCE(SUM(Have), 0) as total_issues, "
            "COALESCE(SUM(Total), 0) as total_expected "
            "FROM comics WHERE Status != 'Paused'"
        )
        if stats:
            total_expected = stats.get("total_expected", 0) or 0
            total_issues = stats.get("total_issues", 0) or 0
            result["stats"] = {
                "total_series": stats.get("total_series", 0),
                "total_issues": total_issues,
                "total_expected": total_expected,
                "completion_pct": round(total_issues / total_expected * 100, 1) if total_expected > 0 else 0,
            }
            result["stats"].setdefault("queue_count", 0)

        # Manga-specific stats
        manga_stats = db.DBConnection().selectone(
            "SELECT COUNT(*) as manga_series, "
            "COALESCE(SUM(Have), 0) as manga_have, "
            "COALESCE(SUM(Total), 0) as manga_total "
            "FROM comics WHERE Status != 'Paused' AND ContentType = 'manga'"
        )
        if manga_stats:
            manga_total = manga_stats.get("manga_total", 0) or 0
            manga_have = manga_stats.get("manga_have", 0) or 0
            result["stats"]["manga_series"] = manga_stats.get("manga_series", 0)
            result["stats"]["manga_have"] = manga_have
            result["stats"]["manga_total"] = manga_total
            result["stats"]["manga_completion_pct"] = round(manga_have / manga_total * 100, 1) if manga_total > 0 else 0

        # Comic-specific stats (non-manga)
        comic_stats = db.DBConnection().selectone(
            "SELECT COUNT(*) as comic_series, "
            "COALESCE(SUM(Have), 0) as comic_have, "
            "COALESCE(SUM(Total), 0) as comic_total "
            "FROM comics WHERE Status != 'Paused' AND (ContentType IS NULL OR ContentType = 'comic')"
        )
        if comic_stats:
            result["stats"]["comic_series"] = comic_stats.get("comic_series", 0)
            result["stats"]["comic_have"] = comic_stats.get("comic_have", 0) or 0
            result["stats"]["comic_total"] = comic_stats.get("comic_total", 0) or 0
    except Exception as e:
        logger.error("[DASHBOARD] Error fetching stats: %s" % e)

    # Queue KPI and preview deliberately share the active DDL predicate.
    try:
        result["stats"]["queue_count"] = dl_queries.count_active_ddl_items()
    except Exception as e:
        logger.error("[DASHBOARD] Error fetching active queue count: %s" % e)
        result["stats"].setdefault("queue_count", 0)

    try:
        result["active_queue"] = dl_queries.get_active_ddl_preview(limit=5)
    except Exception as e:
        logger.error("[DASHBOARD] Error fetching active queue preview: %s" % e)

    # AI activity: last 5 entries (only if AI configured)
    # Check both runtime client and saved config (client requires restart)
    ai_base_url = getattr(comicarr.CONFIG, "AI_BASE_URL", None)
    if comicarr.AI_CLIENT is not None or ai_base_url:
        result["ai_configured"] = True
        try:
            activity = db.DBConnection().select(
                "SELECT timestamp, feature_type, action_description, "
                "prompt_tokens, completion_tokens, success "
                "FROM ai_activity_log ORDER BY timestamp DESC LIMIT 5"
            )
            result["ai_activity"] = activity or []
        except Exception as e:
            logger.error("[DASHBOARD] Error fetching AI activity: %s" % e)

    return result
