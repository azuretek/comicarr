#  Copyright (C) 2025–2026 Comicarr contributors
#
#  This file is part of Comicarr.
#
#  Comicarr is free software: you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.

"""Activity Center read service — shapes query results for HTTP handlers."""

from comicarr.app.activity import grouping, queries


def get_timeline(limit=None, offset=None, scope_type=None, scope_id=None):
    """Paginated narrative timeline events (not pre-grouped stories)."""
    return queries.list_timeline_events(
        limit=limit,
        offset=offset,
        scope_type=scope_type,
        scope_id=scope_id,
    )


def get_attention_band(scope_type=None, scope_id=None):
    """Needs-attention **groups**, newest first, with a stable list envelope.

    ``total`` counts groups (the same number the status line shows);
    ``member_total`` counts the journal rows behind them. The band preview
    renders the first ``preview_cap`` groups and folds the rest into the
    triage route (#526).
    """
    groups = queries.list_attention_groups(scope_type=scope_type, scope_id=scope_id)
    return {
        "results": groups,
        "total": len(groups),
        "member_total": sum(group["member_count"] for group in groups),
        "preview_cap": grouping.BAND_PREVIEW_CAP,
    }


def get_status():
    """Open-work counts for the global quiet-counts status indicator."""
    return queries.get_open_work_counts()
