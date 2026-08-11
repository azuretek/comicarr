#  Copyright (C) 2026 Comicarr contributors
#
#  This file is part of Comicarr.
#
#  Comicarr is free software: you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.

"""Where the log level comes from: startup args, then the environment, then config.

`docs/architecture/logging-levels.md` fixes what each level *means*; this module
fixes where the number is *read from*. Three sources, highest first:

1. a startup argument (`--log-level`, or its `--verbose`/`--quiet` aliases)
2. the `COMICARR_LOG_LEVEL` environment variable
3. `LOG_LEVEL` in the config file (the Settings UI writes this one)

A source only counts when it *explicitly supplies* a value. That qualifier is
the whole point: Docker used to pass `--quiet` on every start, which pinned the
escape hatch permanently open and left an operator with no way to raise
verbosity (#610). An argument that was not passed must leave the layer below it
alone.

`COMICARR_LOG_LEVEL` is a deliberate one-off for this key, not the first step of
a general `COMICARR_<KEY>` override mechanism -- that raises precedence,
secrets, and UI-honesty questions of its own and is out of scope here.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Mapping

ENV_VAR = "COMICARR_LOG_LEVEL"

MIN_LEVEL = 0
MAX_LEVEL = 2

# Named for the source, not the mechanism, because these strings are echoed to
# the operator when the level is decided.
SOURCE_ARGUMENT = "startup argument"
SOURCE_ENVIRONMENT = f"the {ENV_VAR} environment variable"
SOURCE_CONFIG = "the config file"
SOURCE_DEFAULT = "the built-in default"
# Not a startup source -- the Settings page writes `LOG_LEVEL` while the process
# is running, and `resolve_startup_log_level` re-decides it on the next start.
# It shares `parse_level` so a level typed into the UI is read by exactly the
# same rules as one passed on the command line.
SOURCE_SETTINGS = "the Settings page"


@dataclass
class LogLevelResolution:
    """The level to start with, where it came from, and what to tell the operator."""

    level: int
    source: str
    notices: list[str] = field(default_factory=list)


def clamp_level(level: int) -> int:
    """Hold a level inside the dial's range, matching `threshold_for_level`."""
    return max(MIN_LEVEL, min(MAX_LEVEL, level))


def parse_level(raw, origin: str) -> tuple[int | None, list[str]]:
    """Read one source's value into a usable level.

    Returns `(None, notices)` when the source supplied nothing usable, so the
    caller falls through to the next layer rather than starting at a level
    nobody asked for. Out-of-range numbers are clamped rather than rejected: a
    compose file asking for `3` wants maximum verbosity, and refusing to boot
    over it helps nobody.
    """
    notices: list[str] = []
    if raw is None:
        return None, notices
    if isinstance(raw, bool):  # bool is an int subclass; never a level
        return None, [f"Ignoring {origin}: {raw!r} is not a log level."]
    if isinstance(raw, int):
        parsed = raw
    else:
        text = str(raw).strip()
        if not text:
            return None, notices
        try:
            parsed = int(text)
        except ValueError:
            return None, [f"Ignoring {origin}: {text!r} is not a number. Expected {MIN_LEVEL}-{MAX_LEVEL}."]
    clamped = clamp_level(parsed)
    if clamped != parsed:
        notices.append(f"Log level {parsed} from {origin} is out of range; using {clamped}.")
    return clamped, notices


def resolve_startup_log_level(
    argument_level=None,
    config_level=None,
    environ: Mapping[str, str] | None = None,
) -> LogLevelResolution:
    """Pick the level to start with from the three sources, highest priority first."""
    environ = os.environ if environ is None else environ
    notices: list[str] = []

    candidates = (
        (argument_level, SOURCE_ARGUMENT),
        (environ.get(ENV_VAR), SOURCE_ENVIRONMENT),
        (config_level, SOURCE_CONFIG),
    )

    supplied: list[tuple[int, str]] = []
    for raw, source in candidates:
        level, source_notices = parse_level(raw, source)
        notices.extend(source_notices)
        if level is not None:
            supplied.append((level, source))

    if not supplied:
        return LogLevelResolution(level=1, source=SOURCE_DEFAULT, notices=notices)

    level, source = supplied[0]
    # Say what lost, so an operator who edits the Settings dial and sees nothing
    # change has the reason in front of them rather than in the source.
    overridden = [
        f"{other_level} from {other_source}" for other_level, other_source in supplied[1:] if other_level != level
    ]
    if overridden:
        notices.append(f"Log level {level} from {source} overrides {', '.join(overridden)}.")
    return LogLevelResolution(level=level, source=source, notices=notices)
