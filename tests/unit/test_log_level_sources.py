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
    ACCEPTED_FORMS,
    ENV_VAR,
    SOURCE_ARGUMENT,
    SOURCE_CONFIG,
    SOURCE_DEFAULT,
    SOURCE_ENVIRONMENT,
    clamp_level,
    describe_level,
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


class TestNames:
    """Both notations mean the same thing, from every source (#620)."""

    @pytest.mark.parametrize(("name", "expected"), [("warning", 0), ("info", 1), ("debug", 2)])
    def test_each_level_has_a_name(self, name, expected):
        level, notices = parse_level(name, "test")
        assert level == expected
        assert notices == []

    @pytest.mark.parametrize("spelling", ["DEBUG", "Debug", "  debug  "])
    def test_names_are_case_insensitive_and_trimmed(self, spelling):
        level, _ = parse_level(spelling, "test")
        assert level == 2

    def test_a_name_wins_from_the_environment_like_a_number_would(self):
        resolution = resolve_startup_log_level(argument_level=None, config_level=0, environ={ENV_VAR: "debug"})
        assert resolution.level == 2
        assert resolution.source == SOURCE_ENVIRONMENT

    def test_a_name_in_the_config_file_is_read_too(self):
        """Nothing writes one, but a hand-edited config.ini must not be narrower."""
        resolution = resolve_startup_log_level(argument_level=None, config_level="warning", environ={})
        assert resolution.level == 0
        assert resolution.source == SOURCE_CONFIG

    @pytest.mark.parametrize("rejected", ["quiet", "normal", "verbose"])
    def test_the_retired_vocabulary_is_not_accepted_as_a_value(self, rejected):
        """`--log-level` was type=int, so nobody could ever have typed these."""
        level, notices = parse_level(rejected, "test")
        assert level is None
        assert notices

    @pytest.mark.parametrize("rejected", ["warn", "error", "critical"])
    def test_names_no_level_can_honour_are_refused(self, rejected):
        """`error` would have to mean level 0, which also emits warnings."""
        level, notices = parse_level(rejected, "test")
        assert level is None
        assert notices

    def test_describe_level_carries_both_notations(self):
        assert [describe_level(level) for level in (0, 1, 2)] == ["0 (warning)", "1 (info)", "2 (debug)"]

    def test_accepted_forms_names_both_notations(self):
        for form in ("0-2", "warning", "info", "debug"):
            assert form in ACCEPTED_FORMS


class TestUnusableValues:
    def test_an_unrecognised_environment_value_is_ignored_not_fatal(self):
        resolution = resolve_startup_log_level(argument_level=None, config_level=1, environ={ENV_VAR: "loud"})
        assert resolution.level == 1
        assert resolution.source == SOURCE_CONFIG
        assert any("'loud'" in notice for notice in resolution.notices)

    def test_the_rejection_notice_names_both_accepted_forms(self):
        _, notices = parse_level("loud", "test")
        assert any(ACCEPTED_FORMS in notice for notice in notices)

    def test_an_out_of_range_value_is_clamped_rather_than_rejected(self):
        resolution = resolve_startup_log_level(argument_level=None, config_level=1, environ={ENV_VAR: "7"})
        assert resolution.level == 2
        assert resolution.source == SOURCE_ENVIRONMENT
        assert any("out of range" in notice for notice in resolution.notices)

    def test_a_negative_value_clamps_to_warning(self):
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
        assert any(f"overrides 0 (warning) from {SOURCE_CONFIG}" in notice for notice in resolution.notices)

    def test_an_override_notice_names_the_winner_in_both_notations(self):
        resolution = resolve_startup_log_level(argument_level=2, config_level=0, environ={})
        assert any(f"Log level 2 (debug) from {SOURCE_ARGUMENT}" in notice for notice in resolution.notices)

    def test_a_clamp_notice_names_the_level_it_settled_on(self):
        resolution = resolve_startup_log_level(argument_level=None, config_level=None, environ={ENV_VAR: "7"})
        assert any("using 2 (debug)" in notice for notice in resolution.notices)

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
