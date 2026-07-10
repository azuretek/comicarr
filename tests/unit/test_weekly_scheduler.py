"""Weekly scheduler lifecycle regression tests."""

import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

import comicarr
from comicarr import weeklypullit
from comicarr.app.system import service as system_service


def test_weekly_run_records_success_and_returns_to_waiting(monkeypatch):
    job_management = MagicMock()
    monkeypatch.setattr(weeklypullit.helpers, "job_management", job_management)
    monkeypatch.setattr(weeklypullit.helpers, "utctimestamp", lambda: 123.0)
    monkeypatch.setattr(weeklypullit.weeklypull, "pullit", MagicMock())
    monkeypatch.setattr(weeklypullit.weeklypull, "future_check", MagicMock())
    monkeypatch.setattr(comicarr, "WEEKLY_STATUS", "Queued")

    weeklypullit.Weekly().run()

    assert comicarr.WEEKLY_STATUS == "Waiting"
    assert job_management.call_args_list[-1].kwargs == {
        "write": True,
        "job": "Weekly Pullist",
        "last_run_completed": 123.0,
        "status": "Waiting",
    }


def test_weekly_run_records_failure_and_recovers_status(monkeypatch):
    job_management = MagicMock()
    monkeypatch.setattr(weeklypullit.helpers, "job_management", job_management)
    monkeypatch.setattr(weeklypullit.helpers, "utctimestamp", lambda: 456.0)
    monkeypatch.setattr(weeklypullit.weeklypull, "pullit", MagicMock(side_effect=RuntimeError("upstream down")))
    monkeypatch.setattr(weeklypullit.weeklypull, "future_check", MagicMock())
    monkeypatch.setattr(comicarr, "WEEKLY_STATUS", "Queued")

    weeklypullit.Weekly().run()

    assert comicarr.WEEKLY_STATUS == "Error"
    failure_call = job_management.call_args_list[-1].kwargs
    assert failure_call["write"] is True
    assert failure_call["job"] == "Weekly Pullist"
    assert failure_call["last_run_completed"] == 456.0
    assert failure_call["status"] == "Error"
    assert failure_call["failure"] is True
    assert str(failure_call["failure_message"]) == "upstream down"


def test_weekly_run_records_returned_pull_failure(monkeypatch):
    job_management = MagicMock()
    monkeypatch.setattr(weeklypullit.helpers, "job_management", job_management)
    monkeypatch.setattr(weeklypullit.helpers, "utctimestamp", lambda: 456.0)
    monkeypatch.setattr(weeklypullit.weeklypull, "pullit", MagicMock(return_value={"status": "failure"}))
    future_check = MagicMock()
    monkeypatch.setattr(weeklypullit.weeklypull, "future_check", future_check)

    weeklypullit.Weekly().run()

    future_check.assert_not_called()
    assert job_management.call_args_list[-1].kwargs["status"] == "Error"
    assert job_management.call_args_list[-1].kwargs["failure"] is True


def test_manual_run_restores_the_original_future_schedule(monkeypatch):
    scheduled_run = datetime.datetime.utcnow() + datetime.timedelta(hours=4)
    job = MagicMock()
    scheduler = MagicMock()
    scheduler.get_job.return_value = job
    monkeypatch.setattr(comicarr, "SCHED", scheduler)
    monkeypatch.setattr(comicarr, "WEEKLY_MANUAL_NEXT_RUN", scheduled_run)

    weeklypullit._restore_manual_next_run()

    job.modify.assert_called_once_with(next_run_time=scheduled_run)
    assert comicarr.WEEKLY_MANUAL_NEXT_RUN is None


def test_manual_refresh_restores_a_real_interval_trigger_schedule(monkeypatch):
    timezone = datetime.timezone.utc
    original_next_run = datetime.datetime.now(timezone) + datetime.timedelta(hours=4)
    scheduler = BackgroundScheduler(timezone=timezone)
    scheduler.add_job(
        lambda: None,
        trigger=IntervalTrigger(hours=4, timezone=timezone),
        id="weekly",
        next_run_time=original_next_run,
    )
    ctx = SimpleNamespace(scheduler=scheduler, weekly_status="Waiting")
    monkeypatch.setattr(comicarr, "WEEKLY_STATUS", "Waiting")
    monkeypatch.setattr(comicarr, "WEEKLY_MANUAL_NEXT_RUN", None)
    monkeypatch.setattr(system_service.db, "upsert", MagicMock())
    monkeypatch.setattr(comicarr, "SCHED", scheduler)

    result = system_service.request_weekly_refresh(ctx)
    weeklypullit._restore_manual_next_run()

    assert result["accepted"] is True
    assert scheduler.get_job("weekly").next_run_time == original_next_run
