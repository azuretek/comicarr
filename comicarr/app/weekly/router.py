#  Copyright (C) 2025-2026 Comicarr contributors
#
#  This file is part of Comicarr.
#
#  Comicarr is free software: you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.

"""
Weekly pull list router — serves weekly release data for the Weekly page.
"""

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from comicarr.app.core.context import AppContext, get_context
from comicarr.app.core.security import require_session
from comicarr.app.storyarcs import service as storyarcs_service
from comicarr.app.system import service as system_service

router = APIRouter(prefix="/api/weekly", tags=["weekly"])


@router.get("", dependencies=[Depends(require_session)])
@router.get("/", dependencies=[Depends(require_session)])
def get_weekly(ctx: AppContext = Depends(get_context)):
    """Return industry releases for the application current Sunday-based week."""
    from comicarr import db, logger

    try:
        week, year = storyarcs_service.get_current_week()
        rows = db.DBConnection().select(
            "SELECT COMIC, ISSUE, PUBLISHER, SHIPDATE, STATUS, ComicID, IssueID "
            "FROM weekly WHERE weeknumber = ? AND year = ? ORDER BY COMIC ASC",
            [str(int(week)), year],
        )
        return rows or []
    except Exception as e:
        logger.error("[WEEKLY] Error fetching weekly data: %s" % e)
        return []


@router.post("/refresh", dependencies=[Depends(require_session)])
def refresh_weekly(ctx: AppContext = Depends(get_context)):
    """Request an immediate run of the existing, coalesced weekly scheduler job."""
    result = system_service.request_weekly_refresh(ctx)
    status_code = 503 if result["state"] == "unavailable" else 202 if result["accepted"] else 200
    return JSONResponse(status_code=status_code, content=result)
