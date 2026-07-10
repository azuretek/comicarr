#  Copyright (C) 2012–2024 Mylar3 contributors
#  Copyright (C) 2025–2026 Comicarr contributors
#
#  This file is part of Comicarr.
#  Originally based on Mylar3 (https://github.com/mylar3/mylar3).
#
#  Comicarr is free software: you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.
#
#  Comicarr is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with Comicarr.  If not, see <http://www.gnu.org/licenses/>.


import datetime

import comicarr
from comicarr import helpers, logger, weeklypull


def _restore_manual_next_run():
    """Restore the recurring schedule displaced by an immediate manual run."""
    scheduled_run = getattr(comicarr, "WEEKLY_MANUAL_NEXT_RUN", None)
    comicarr.WEEKLY_MANUAL_NEXT_RUN = None
    if not isinstance(scheduled_run, datetime.datetime):
        return

    now = datetime.datetime.now(tz=scheduled_run.tzinfo) if scheduled_run.tzinfo else datetime.datetime.utcnow()
    if scheduled_run <= now:
        return

    try:
        job = comicarr.SCHED.get_job("weekly")
        if job is not None:
            job.modify(next_run_time=scheduled_run)
    except Exception as e:
        logger.error("[WEEKLY] Could not restore scheduled refresh time: %s" % e)


class Weekly:
    def __init__(self):
        pass

    def run(self):
        from comicarr.app.system.service import get_weekly_refresh_lock

        with get_weekly_refresh_lock():
            logger.info("[WEEKLY] Checking Weekly Pull-list for new releases/updates")
            helpers.job_management(
                write=True, job="Weekly Pullist", current_run=helpers.utctimestamp(), status="Running"
            )
            comicarr.WEEKLY_STATUS = "Running"
            try:
                pull_result = weeklypull.pullit()
                if isinstance(pull_result, dict) and pull_result.get("status") == "failure":
                    raise RuntimeError("Weekly pull source reported a failure")
                weeklypull.future_check()
            except Exception as e:
                logger.error("[WEEKLY] Pull-list refresh failed: %s" % e)
                _restore_manual_next_run()
                helpers.job_management(
                    write=True,
                    job="Weekly Pullist",
                    last_run_completed=helpers.utctimestamp(),
                    status="Error",
                    failure=True,
                    failure_message=e,
                )
                comicarr.WEEKLY_STATUS = "Error"
                return

            _restore_manual_next_run()
            helpers.job_management(
                write=True, job="Weekly Pullist", last_run_completed=helpers.utctimestamp(), status="Waiting"
            )
            comicarr.WEEKLY_STATUS = "Waiting"
