#  Copyright (C) 2025–2026 Comicarr contributors
#
#  This file is part of Comicarr.
#
#  Comicarr is free software: you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.

"""The log level contract: one dial, applied identically to every sink.

See docs/architecture/logging-levels.md. These tests drive the real
``initLogger`` rather than a stub, because the defects they guard against
(#610/#612) all lived in *handler* state that a call-recording stub cannot see.
"""

import logging

import pytest

import comicarr
from comicarr import logger as comicarr_logger

pytestmark = pytest.mark.skipif(
    not comicarr_logger.LOG_LANG.startswith("en"),
    reason="the non-English RotatingLogger path does not implement this contract yet",
)

LEVEL_THRESHOLDS = {0: logging.WARNING, 1: logging.INFO, 2: logging.DEBUG}


@pytest.fixture
def isolated_logger(tmp_path, monkeypatch):
    """Reconfigure the real 'comicarr' logger, restoring handlers on teardown."""
    lg = logging.getLogger("comicarr")
    saved_handlers = lg.handlers[:]
    saved_level = lg.level
    saved_propagate = lg.propagate
    monkeypatch.setattr(comicarr, "LOG_LEVEL", 1, raising=False)

    def configure(level, console=True):
        comicarr.LOG_LEVEL = level
        comicarr_logger.initLogger(console=console, log_dir=str(tmp_path), loglevel=level)
        return lg

    try:
        yield configure
    finally:
        for handler in lg.handlers[:]:
            lg.removeHandler(handler)
            handler.close()
        for handler in saved_handlers:
            lg.addHandler(handler)
        lg.setLevel(saved_level)
        lg.propagate = saved_propagate


def _sink_levels(lg):
    return {type(handler).__name__: handler.level for handler in lg.handlers}


@pytest.mark.parametrize("level, threshold", sorted(LEVEL_THRESHOLDS.items()))
def test_every_sink_follows_the_dial(isolated_logger, level, threshold):
    lg = isolated_logger(level)

    assert lg.level == threshold
    sinks = _sink_levels(lg)
    assert sinks["RotatingFileHandler"] == threshold
    assert sinks["StreamHandler"] == threshold
    assert sinks["LogListHandler"] == threshold


def test_level_zero_is_warnings_not_silence(isolated_logger):
    """Turning the dial down must not hide the fact that something broke."""
    lg = isolated_logger(0)

    assert lg.isEnabledFor(logging.WARNING)
    assert lg.isEnabledFor(logging.ERROR)
    assert not lg.isEnabledFor(logging.INFO)


def test_turning_the_dial_down_takes_effect(isolated_logger):
    """Regression: level 0 never called setLevel, so 2 -> 0 stayed at DEBUG.

    The old code only set a level for loglevel 1 and >= 2, so lowering
    verbosity at runtime silently kept the previous, more verbose threshold —
    and a fresh level-0 start inherited root's WARNING by accident rather than
    by intent.
    """
    isolated_logger(2)
    lg = isolated_logger(0)

    assert lg.level == logging.WARNING
    assert not lg.isEnabledFor(logging.DEBUG)


def test_raising_verbosity_keeps_the_console_attached(isolated_logger):
    """Regression for #610: raising verbosity used to remove the console sink."""
    for level in (0, 1, 2):
        lg = isolated_logger(level)
        assert "StreamHandler" in _sink_levels(lg), "console lost at level %s" % level


def test_console_can_still_be_detached_explicitly(isolated_logger):
    """Console attachment is a deployment concern, not a verbosity one."""
    lg = isolated_logger(2, console=False)

    assert "StreamHandler" not in _sink_levels(lg)
    assert lg.level == logging.DEBUG


@pytest.mark.parametrize(
    "level, threshold",
    [
        (None, logging.INFO),
        (-1, logging.WARNING),
        (0, logging.WARNING),
        (1, logging.INFO),
        (2, logging.DEBUG),
        (5, logging.DEBUG),
    ],
)
def test_threshold_for_level_maps_the_whole_dial(level, threshold):
    assert comicarr_logger.threshold_for_level(level) == threshold


@pytest.mark.parametrize("configured, expected", [(None, 0), (0, 0), (1, 1), (2, 2)])
def test_current_log_level_treats_unconfigured_as_quiet(monkeypatch, configured, expected):
    monkeypatch.setattr(comicarr, "LOG_LEVEL", configured, raising=False)

    assert comicarr_logger.current_log_level() == expected
