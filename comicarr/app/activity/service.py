#  Copyright (C) 2025–2026 Comicarr contributors
#
#  This file is part of Comicarr.
#
#  Comicarr is free software: you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.

"""Activity Center read service — shapes query results for HTTP handlers."""

from comicarr.app.activity import queries


def get_timeline(limit=None, offset=None, scope_type=None, scope_id=None):
    """Paginated narrative timeline events (not pre-grouped stories)."""
    return queries.list_timeline_events(
        limit=limit,
        offset=offset,
        scope_type=scope_type,
        scope_id=scope_id,
    )


def get_attention_band(scope_type=None, scope_id=None):
    """Needs-attention band rows with a stable list envelope."""
    rows = queries.list_attention_band(scope_type=scope_type, scope_id=scope_id)
    return {"results": rows, "total": len(rows)}


def get_status():
    """Open-work counts for the global quiet-counts status indicator."""
    return queries.get_open_work_counts()
