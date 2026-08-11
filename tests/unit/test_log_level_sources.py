#  Copyright (C) 2026 Comicarr contributors
#
#  This file is part of Comicarr.
#
#  Comicarr is free software: you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.

"""Where the log level comes from: startup argument > COMICARR_LOG_LEVEL > config.

The rule these guard is "a source counts only when it explicitly supplies a
value". Docker passing `--quiet` unconditionally is what pinned the escape hatch
open in #610, so an argument that was not passed must leave the layers below it
alone. See docs/architecture/logging-levels.md.
"""

import pytest

from comicarr.app.config.log_level import (
    ENV_VAR,
    SOURCE_ARGUMENT,
    SOURCE_CONFIG,
    SOURCE_DEFAULT,
    SOURCE_ENVIRONMENT,
    clamp_level,
    parse_level,
    resolve_startup_log_level,
)


class TestPrecedence:
    def test_argument_wins_over_environment_and_config(self):
        resolution = resolve_startup_log_level(
            argument_level=0,
            config_level=1,
            environ={ENV_VAR: "2"},
        )
        assert resolution.level == 0
        assert resolution.source == SOURCE_ARGUMENT

    def test_environment_wins_over_config_when_no_argument(self):
        resolution = resolve_startup_log_level(argument_level=None, config_level=0, environ={ENV_VAR: "2"})
        assert resolution.level == 2
        assert resolution.source == SOURCE_ENVIRONMENT

    def test_config_is_used_when_nothing_else_supplies_a_value(self):
        resolution = resolve_startup_log_level(argument_level=None, config_level=2, environ={})
        assert resolution.level == 2
        assert resolution.source == SOURCE_CONFIG

    def test_no_source_at_all_falls_back_to_normal(self):
        resolution = resolve_startup_log_level(argument_level=None, config_level=None, environ={})
        assert resolution.level == 1
        assert resolution.source == SOURCE_DEFAULT

    def test_level_zero_from_an_argument_is_an_explicit_value_not_an_absent_one(self):
        """0 is falsy; the layer below must not be consulted because of that."""
        resolution = resolve_startup_log_level(argument_level=0, config_level=2, environ={ENV_VAR: "2"})
        assert resolution.level == 0

    def test_level_zero_in_the_environment_is_an_explicit_value(self):
        resolution = resolve_startup_log_level(argument_level=None, config_level=2, environ={ENV_VAR: "0"})
        assert resolution.level == 0
        assert resolution.source == SOURCE_ENVIRONMENT

    def test_level_zero_in_the_config_is_an_explicit_value(self):
        resolution = resolve_startup_log_level(argument_level=None, config_level=0, environ={})
        assert resolution.level == 0
        assert resolution.source == SOURCE_CONFIG

    def test_an_unset_environment_variable_leaves_config_in_charge(self):
        resolution = resolve_startup_log_level(argument_level=None, config_level=2, environ={})
        assert resolution.source == SOURCE_CONFIG

    def test_an_empty_environment_variable_leaves_config_in_charge(self):
        """`COMICARR_LOG_LEVEL=` in a compose file must not mean "level 0"."""
        resolution = resolve_startup_log_level(argument_level=None, config_level=2, environ={ENV_VAR: "  "})
        assert resolution.level == 2
        assert resolution.source == SOURCE_CONFIG

    def test_os_environ_is_read_when_no_mapping_is_passed(self, monkeypatch):
        monkeypatch.setenv(ENV_VAR, "2")
        resolution = resolve_startup_log_level(argument_level=None, config_level=0)
        assert resolution.level == 2
        assert resolution.source == SOURCE_ENVIRONMENT


class TestUnusableValues:
    def test_a_non_numeric_environment_value_is_ignored_not_fatal(self):
        resolution = resolve_startup_log_level(argument_level=None, config_level=1, environ={ENV_VAR: "debug"})
        assert resolution.level == 1
        assert resolution.source == SOURCE_CONFIG
        assert any("'debug'" in notice for notice in resolution.notices)

    def test_an_out_of_range_value_is_clamped_rather_than_rejected(self):
        resolution = resolve_startup_log_level(argument_level=None, config_level=1, environ={ENV_VAR: "7"})
        assert resolution.level == 2
        assert resolution.source == SOURCE_ENVIRONMENT
        assert any("out of range" in notice for notice in resolution.notices)

    def test_a_negative_value_clamps_to_quiet(self):
        resolution = resolve_startup_log_level(argument_level=None, config_level=1, environ={ENV_VAR: "-3"})
        assert resolution.level == 0

    def test_surrounding_whitespace_is_tolerated(self):
        resolution = resolve_startup_log_level(argument_level=None, config_level=1, environ={ENV_VAR: " 2 "})
        assert resolution.level == 2

    @pytest.mark.parametrize("value", [True, False])
    def test_a_boolean_is_never_a_level(self, value):
        """`-q`/`-v` are store_true flags; a caller must map them, not pass them."""
        level, notices = parse_level(value, "test")
        assert level is None
        assert notices

    def test_clamp_level_matches_the_dial_range(self):
        assert [clamp_level(value) for value in (-1, 0, 1, 2, 3)] == [0, 0, 1, 2, 2]


class TestNotices:
    def test_an_override_says_what_it_overrode(self):
        resolution = resolve_startup_log_level(argument_level=2, config_level=0, environ={})
        assert any(f"overrides 0 from {SOURCE_CONFIG}" in notice for notice in resolution.notices)

    def test_every_losing_source_is_named_not_just_the_config(self):
        resolution = resolve_startup_log_level(argument_level=0, config_level=1, environ={ENV_VAR: "2"})
        notice = " ".join(resolution.notices)
        assert SOURCE_ENVIRONMENT in notice
        assert SOURCE_CONFIG in notice

    def test_no_override_notice_when_the_sources_agree(self):
        resolution = resolve_startup_log_level(argument_level=1, config_level=1, environ={ENV_VAR: "1"})
        assert resolution.notices == []

    def test_a_bad_environment_value_is_still_reported_when_an_argument_wins(self):
        """The operator's typo is worth surfacing even though it changed nothing."""
        resolution = resolve_startup_log_level(argument_level=2, config_level=1, environ={ENV_VAR: "loud"})
        assert any("'loud'" in notice for notice in resolution.notices)
