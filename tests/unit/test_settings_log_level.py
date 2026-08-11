#  Copyright (C) 2026 Comicarr contributors
#
#  This file is part of Comicarr.
#
#  Comicarr is free software: you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.

"""Saving the log level from Settings takes effect now, not at the next start.

``logger.configure_log_level`` has performed the live reconfigure all along;
its only caller was maintenance mode, so ``LOG_LEVEL`` was writable, invisible,
and inert until startup -- where a startup argument beat it anyway. The point
of raising verbosity is to catch a problem *while it is happening* (#610), so a
dial that needs a restart destroys the state the operator was trying to
capture.

These tests drive the real ``comicarr`` logger through the real
``update_config`` and assert on what actually gets *emitted*. A call-recording
stub would pass against handlers that never changed.
"""

import logging

import pytest

import comicarr
from comicarr import logger as comicarr_logger
from comicarr.app.core.context import AppContext
from comicarr.app.system import service as system_service

pytestmark = pytest.mark.skipif(
    not comicarr_logger.LOG_LANG.startswith("en"),
    reason="the non-English RotatingLogger path does not implement this contract yet",
)


class FakeConfig:
    """Enough config to persist a level and rebuild the handlers over it.

    Deliberately not a MagicMock: ``configure_log_level`` reads ``LOG_DIR``,
    ``MAX_LOGSIZE`` and ``MAX_LOGFILES`` straight off ``comicarr.CONFIG`` and
    hands them to a real ``RotatingFileHandler``, which a Mock attribute would
    fail on rather than exercise.
    """

    def __init__(self, log_dir):
        self.LOG_DIR = log_dir
        self.MAX_LOGSIZE = 1000000
        self.MAX_LOGFILES = 5
        self.LOG_LEVEL = 1
        self.COMIC_DIR = "/comics"
        self.EXTRA_NEWZNABS = []
        self.EXTRA_TORZNABS = []
        self.persist = True
        self.transactions = []

    def apply_transaction(self, values, configure=True):
        self.transactions.append(dict(values))
        if not self.persist:
            return False
        for key, value in values.items():
            setattr(self, key.upper(), value)
        return True


@pytest.fixture
def settings_save(tmp_path, monkeypatch):
    """Save config through the real service against the real logger.

    Restores the process logger on teardown -- these tests tear down and
    rebuild its handlers, which would otherwise leak into every later test.
    """
    lg = logging.getLogger("comicarr")
    saved_handlers = lg.handlers[:]
    saved_level = lg.level
    saved_propagate = lg.propagate

    config = FakeConfig(str(tmp_path))
    ctx = AppContext(config=config, data_dir=str(tmp_path))
    monkeypatch.setattr(comicarr, "CONFIG", config, raising=False)
    monkeypatch.setattr(comicarr, "LOG_LEVEL", 1, raising=False)
    monkeypatch.setattr(comicarr, "LOGLIST", [], raising=False)
    comicarr_logger.initLogger(console=True, log_dir=str(tmp_path), loglevel=1)

    def save(**key_values):
        return system_service.update_config(ctx, key_values)

    save.config = config
    save.ctx = ctx
    save.logger = lg

    try:
        yield save
    finally:
        for handler in lg.handlers[:]:
            lg.removeHandler(handler)
            handler.close()
        for handler in saved_handlers:
            lg.addHandler(handler)
        lg.setLevel(saved_level)
        lg.propagate = saved_propagate


def _emitted(message):
    """Whether a record reached the Web UI sink, rather than merely being sent."""
    return any(message in entry[1] for entry in comicarr.LOGLIST)


class TestASavedLevelChangesWhatIsEmitted:
    def test_raising_the_level_starts_emitting_debug(self, settings_save):
        comicarr_logger.debug("before-raise")
        assert not _emitted("before-raise")

        result = settings_save(log_level=2)

        assert result == {"success": True}
        comicarr_logger.debug("after-raise")
        assert _emitted("after-raise")

    def test_lowering_the_level_stops_emitting_info(self, settings_save):
        settings_save(log_level=0)

        comicarr_logger.info("after-lower")

        assert not _emitted("after-lower")
        assert settings_save.logger.isEnabledFor(logging.WARNING)

    def test_every_sink_follows_the_saved_level(self, settings_save):
        settings_save(log_level=2)

        sinks = {type(handler).__name__: handler.level for handler in settings_save.logger.handlers}

        assert settings_save.logger.level == logging.DEBUG
        assert sinks["RotatingFileHandler"] == logging.DEBUG
        assert sinks["LogListHandler"] == logging.DEBUG
        assert sinks["StreamHandler"] == logging.DEBUG

    def test_the_saved_level_becomes_the_level_in_force(self, settings_save):
        """Whoever asks the dial afterwards must get the level just saved."""
        settings_save(log_level=2)

        assert comicarr_logger.current_log_level() == 2
        assert settings_save.config.LOG_LEVEL == 2

    def test_the_level_is_persisted_as_well_as_applied(self, settings_save):
        """Live is not enough on its own -- the next start reads the file."""
        settings_save(log_level=0)

        assert settings_save.config.transactions == [{"LOG_LEVEL": 0}]


class TestTheValueIsReadByTheSameRulesAsEverySource:
    @pytest.mark.parametrize("raw, expected", [("2", 2), (0, 0), ("0", 0)])
    def test_a_numeric_string_is_a_level(self, settings_save, raw, expected):
        assert settings_save(log_level=raw) == {"success": True}
        assert comicarr_logger.current_log_level() == expected

    @pytest.mark.parametrize("raw, clamped", [(5, 2), (-1, 0)])
    def test_out_of_range_clamps_and_persists_the_clamped_value(self, settings_save, raw, clamped):
        """A compose file asking for 3 wants maximum verbosity; so does an operator.

        The clamped value is what gets written, so config.ini cannot claim a
        level the running process is not honouring.
        """
        assert settings_save(log_level=raw) == {"success": True}

        assert settings_save.config.LOG_LEVEL == clamped
        assert comicarr_logger.current_log_level() == clamped

    @pytest.mark.parametrize("raw", ["verbose", True, 2.5])
    def test_a_non_level_is_refused_rather_than_persisted(self, settings_save, raw):
        """Persisting garbage would be ignored at the next start -- silently.

        Startup sources fall through to the next layer instead of refusing to
        boot. An HTTP request has somewhere to put the complaint.
        """
        result = settings_save(log_level=raw)

        assert result["success"] is False
        assert "LOG_LEVEL must be a number between 0 and 2" == result["error"]
        assert settings_save.config.transactions == []
        assert comicarr_logger.current_log_level() == 1


class TestTheRunningLevelOnlyFollowsADurableSave:
    def test_a_failed_save_leaves_the_running_level_alone(self, settings_save):
        settings_save.config.persist = False

        result = settings_save(log_level=2)

        assert result["success"] is False
        assert comicarr_logger.current_log_level() == 1
        comicarr_logger.debug("after-failed-save")
        assert not _emitted("after-failed-save")

    def test_a_save_that_persists_but_cannot_reconfigure_still_succeeds(self, settings_save, monkeypatch):
        """The level survives the restart; reporting a failed save would not.

        Rebuilding the handlers can fail on a log directory that has become
        unwritable. Losing the durable write over that is the worse outcome.
        """
        monkeypatch.setattr(
            comicarr_logger,
            "configure_log_level",
            lambda level: (_ for _ in ()).throw(FileNotFoundError("log dir vanished")),
        )

        result = settings_save(log_level=2)

        assert result == {"success": True}
        assert settings_save.config.LOG_LEVEL == 2

    def test_saving_an_unrelated_key_does_not_touch_the_logger(self, settings_save, monkeypatch):
        calls = []
        monkeypatch.setattr(comicarr_logger, "configure_log_level", lambda level: calls.append(level))

        assert settings_save(comic_dir="/new/comics") == {"success": True}

        assert calls == []
