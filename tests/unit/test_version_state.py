#  Copyright (C) 2026 Comicarr contributors
#
#  This file is part of Comicarr.
#
#  Comicarr is free software: you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.

"""Version state written after startup must reach the API.

The runtime context is built once, from a snapshot of the module globals. The
scheduled version check wrote only the globals, so every result after boot
landed in a copy nobody reads and the update banner could never appear.
"""

from unittest.mock import MagicMock, patch

import pytest

import comicarr
from comicarr import versioncheck
from comicarr.app.config.registry import REGISTRY
from comicarr.app.core.context import AppContext
from comicarr.app.system import service as system_service


def test_git_user_default_is_project_owner():
    """Out-of-box update checks must hit frankieramirez/comicarr, not comicarr/comicarr.

    The latter resolves to an unrelated third-party repo, so a 404 looks like
    "no releases" rather than a misconfigured owner. Regression for #456.
    """
    assert REGISTRY["GIT_USER"].default == "frankieramirez"


@pytest.fixture
def ctx(monkeypatch):
    config = MagicMock(GIT_USER="frankieramirez", GIT_BRANCH="main", GIT_TOKEN=None, AUTO_UPDATE=False)
    context = AppContext(
        prog_dir="/tmp/comicarr_test",
        data_dir="/tmp/comicarr_test/data",
        db_file=":memory:",
        config=config,
        scheduler=MagicMock(),
        current_version="aaaaaaa",
        latest_version="aaaaaaa",
        commits_behind=0,
    )
    # checkGithub still reads config and install type off the module.
    monkeypatch.setattr(comicarr, "CONFIG", config, raising=False)
    monkeypatch.setattr(comicarr, "INSTALL_TYPE", "git", raising=False)
    monkeypatch.setattr(comicarr, "CURRENT_VERSION", "aaaaaaa", raising=False)
    with patch("comicarr.app.core.runtime.get_runtime_if_initialized", return_value=context):
        yield context


def _github_response(payload):
    response = MagicMock()
    response.json.return_value = payload
    return response


class TestScheduledVersionCheckReachesTheApi:
    def test_new_commit_moves_latest_version_and_commits_behind(self, ctx):
        responses = [
            _github_response({"sha": "bbbbbbb"}),
            _github_response({"total_commits": 3}),
        ]

        with patch.object(versioncheck.requests, "get", side_effect=responses):
            versioncheck.checkGithub(current_version="aaaaaaa")

        info = system_service.get_version_info(ctx)
        assert info["latest_version"] == "bbbbbbb"
        assert info["commits_behind"] == 3

    def test_legacy_globals_stay_in_step(self, ctx):
        responses = [
            _github_response({"sha": "ccccccc"}),
            _github_response({"total_commits": 1}),
        ]

        with patch.object(versioncheck.requests, "get", side_effect=responses):
            versioncheck.checkGithub(current_version="aaaaaaa")

        assert comicarr.LATEST_VERSION == "ccccccc"
        assert comicarr.COMMITS_BEHIND == 1
        assert ctx.latest_version == comicarr.LATEST_VERSION
        assert ctx.commits_behind == comicarr.COMMITS_BEHIND

    def test_github_failure_still_records_a_result(self, ctx):
        with patch.object(versioncheck.requests, "get", side_effect=RuntimeError("no network")):
            versioncheck.checkGithub(current_version="aaaaaaa")

        assert system_service.get_version_info(ctx)["commits_behind"] == 0


class TestATransientOutageDoesNotClearAKnownUpdate:
    """A failed check must not report 0 -- that reads as "up to date".

    Before these writes reached the runtime context they were inert, so a
    failure could not affect the API. Now that they land, publishing 0 on
    failure would silently replace a real "update available" with a false
    negative until the next successful check.
    """

    def test_first_request_failure_preserves_the_last_known_count(self, ctx):
        responses = [
            _github_response({"sha": "bbbbbbb"}),
            _github_response({"total_commits": 3}),
        ]
        with patch.object(versioncheck.requests, "get", side_effect=responses):
            versioncheck.checkGithub(current_version="aaaaaaa")
        assert system_service.get_version_info(ctx)["commits_behind"] == 3

        with patch.object(versioncheck.requests, "get", side_effect=RuntimeError("no network")):
            versioncheck.checkGithub(current_version="aaaaaaa")

        assert system_service.get_version_info(ctx)["commits_behind"] == 3

    def test_compare_request_failure_preserves_the_last_known_count(self, ctx):
        responses = [
            _github_response({"sha": "bbbbbbb"}),
            _github_response({"total_commits": 2}),
        ]
        with patch.object(versioncheck.requests, "get", side_effect=responses):
            versioncheck.checkGithub(current_version="aaaaaaa")
        assert system_service.get_version_info(ctx)["commits_behind"] == 2

        # First call succeeds, the compare call fails.
        responses = [_github_response({"sha": "ccccccc"}), RuntimeError("no network")]
        with patch.object(versioncheck.requests, "get", side_effect=responses):
            versioncheck.checkGithub(current_version="aaaaaaa")

        assert system_service.get_version_info(ctx)["commits_behind"] == 2

    def test_failure_before_any_successful_check_still_seeds_zero(self, ctx):
        versioncheck._set_version_state(commits_behind=None)

        with patch.object(versioncheck.requests, "get", side_effect=RuntimeError("no network")):
            versioncheck.checkGithub(current_version="aaaaaaa")

        assert system_service.get_version_info(ctx)["commits_behind"] == 0


class TestGithubRequestTimeout:
    """Update checks must bound connect/read so a dropped SYN cannot hang forever.

    Issue #455 / #446: failed checks keep retrying on the 360-minute schedule.
    That policy is only safe when each attempt has a hard timeout (10s, 10s).
    """

    def test_check_github_passes_timeout_on_every_request(self, ctx):
        responses = [
            _github_response({"sha": "bbbbbbb"}),
            _github_response({"total_commits": 1}),
        ]
        with patch.object(versioncheck.requests, "get", side_effect=responses) as mock_get:
            versioncheck.checkGithub(current_version="aaaaaaa")

        assert mock_get.call_count == 2
        for call in mock_get.call_args_list:
            assert call.kwargs.get("timeout") == versioncheck._GITHUB_REQUEST_TIMEOUT
        assert versioncheck._GITHUB_REQUEST_TIMEOUT == (10, 10)

    def test_check_github_preserves_auth_with_timeout(self, ctx):
        token = ("ghp_test", "x-oauth-basic")
        comicarr.CONFIG.GIT_TOKEN = token
        responses = [
            _github_response({"sha": "bbbbbbb"}),
            _github_response({"total_commits": 0}),
        ]
        with patch.object(versioncheck.requests, "get", side_effect=responses) as mock_get:
            versioncheck.checkGithub(current_version="aaaaaaa")

        for call in mock_get.call_args_list:
            assert call.kwargs.get("auth") is token
            assert call.kwargs.get("timeout") == (10, 10)

    def test_timeout_error_is_treated_as_a_failed_check(self, ctx):
        with patch.object(
            versioncheck.requests, "get", side_effect=versioncheck.requests.exceptions.Timeout("connect timed out")
        ):
            result = versioncheck.checkGithub(current_version="aaaaaaa")

        assert result["status"] == "failure"
        assert system_service.get_version_info(ctx)["commits_behind"] == 0


class TestVersionStateHelper:
    def test_writes_context_and_legacy_together(self, ctx):
        versioncheck._set_version_state(current_branch="python3-dev")

        assert ctx.current_branch == "python3-dev"
        assert comicarr.CURRENT_BRANCH == "python3-dev"

    def test_falls_back_to_the_module_before_the_runtime_exists(self):
        with patch("comicarr.app.core.runtime.get_runtime_if_initialized", return_value=None):
            versioncheck._set_version_state(current_version="preboot")

        assert comicarr.CURRENT_VERSION == "preboot"

    def test_falls_back_to_the_module_after_disposal(self, ctx):
        ctx.disposed = True

        versioncheck._set_version_state(latest_version="postdispose")

        assert comicarr.LATEST_VERSION == "postdispose"
        assert ctx.latest_version != "postdispose"

    def test_every_mapped_field_exists_on_the_context(self, ctx):
        for field in versioncheck._VERSION_FIELDS:
            assert hasattr(ctx, field), "AppContext is missing %s" % field
