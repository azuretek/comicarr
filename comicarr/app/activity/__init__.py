#  Copyright (C) 2025–2026 Comicarr contributors
#
#  This file is part of Comicarr.
#
#  Comicarr is free software: you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.

"""Activity Center domain — narrative timeline, attention band, open-work reads,
age-based retention, and the sole write facade for activity_events.

Query-backed HTTP reads (#485); daily 90-day purge (#489); write facade (#479);
production producers (#484) live in :mod:`comicarr.app.activity.producers` and
call :func:`comicarr.app.activity.events.record_activity` (and
:func:`publish_activity` after a shared-conn commit). Do not insert into
``activity_events`` or publish the ``activity`` SSE envelope elsewhere.
"""

from comicarr.app.activity.events import (
    LEGAL_CELLS,
    is_legal_cell,
    publish_activity,
    record_activity,
    severity_for,
)

__all__ = [
    "LEGAL_CELLS",
    "is_legal_cell",
    "publish_activity",
    "record_activity",
    "severity_for",
]
