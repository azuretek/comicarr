#  Copyright (C) 2026 Comicarr contributors
#
#  This file is part of Comicarr.
#
#  Comicarr is free software: you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.

"""Semver release check state must reach GET /api/system/version.

Update availability is judged against the Changesets release line (not git
commits). checkGithub writes process state; get_version_info reads it.
"""

from unittest.mock import MagicMock, patch

import pytest

import comicarr
from comicarr import versioncheck
from comicarr.app.config.registry import REGISTRY
from comicarr.app.core.context import AppContext
from comicarr.app.system import service as system_service


def test_git_user_default_is_project_owner():
    """GIT_USER remains the project owner for carepackage/legacy paths; update check ignores it."""
    assert REGISTRY["GIT_USER"].default == "frankieramirez"


def test_check_github_defaults_on():
    """New installs contact GitHub for release checks unless the operator opts out."""
    assert REGISTRY["CHECK_GITHUB"].default is True


def test_auto_update_and_startup_flag_are_retired():
    """AUTO_UPDATE and CHECK_GITHUB_ON_STARTUP no longer exist as config keys."""
    assert "AUTO_UPDATE" not in REGISTRY
    assert "CHECK_GITHUB_ON_STARTUP" not in REGISTRY


def test_config_version_is_sixteen():
    assert REGISTRY["CONFIG_VERSION"].default == 16


@pytest.fixture
def ctx(monkeypatch):
    config = MagicMock(GIT_USER="someone-else", GIT_BRANCH="main", GIT_TOKEN=None, CHECK_GITHUB=True)
    context = AppContext(
        prog_dir="/tmp/comicarr_test",
        data_dir="/tmp/comicarr_test/data",
        db_file=":memory:",
        config=config,
        scheduler=MagicMock(),
        current_version="aaaaaaa",
        latest_version=None,
        update_state="unknown",
        update_reason="never_checked",
        install_type="git",
    )
    monkeypatch.setattr(comicarr, "CONFIG", config, raising=False)
    monkeypatch.setattr(comicarr, "INSTALL_TYPE", "git", raising=False)
    monkeypatch.setattr(comicarr, "CURRENT_VERSION", "aaaaaaa", raising=False)
    monkeypatch.setattr(comicarr, "GLOBAL_MESSAGES", None, raising=False)
    with (
        patch("comicarr.app.core.runtime.get_runtime_if_initialized", return_value=context),
        patch.object(system_service, "get_release_version", return_value="0.20.0"),
        patch.object(versioncheck, "get_release_version", return_value="0.20.0"),
    ):
        yield context


def _github_response(payload, status_code=200, headers=None):
    response = MagicMock()
    response.status_code = status_code
    response.headers = headers or {}
    response.json.return_value = payload
    return response


class TestSemverReleaseCheck:
    def test_behind_when_remote_is_newer(self, ctx):
        with patch.object(
            versioncheck.requests,
            "get",
            return_value=_github_response({"tag_name": "v0.21.0"}),
        ) as mock_get:
            versioncheck.checkGithub()

        info = system_service.get_version_info(ctx)
        assert info["update_state"] == "behind"
        assert info["latest_version"] == "0.21.0"
        assert info["release_version"] == "0.20.0"
        assert info.get("update_reason") in (None, "")
        assert "commits_behind" not in info
        # Constant owner/repo — never reads GIT_USER.
        assert mock_get.call_args.args[0] == versioncheck._GITHUB_RELEASES_LATEST
        assert "frankieramirez/comicarr" in mock_get.call_args.args[0]
        assert "someone-else" not in mock_get.call_args.args[0]

    def test_current_when_versions_match(self, ctx):
        with patch.object(
            versioncheck.requests,
            "get",
            return_value=_github_response({"tag_name": "v0.20.0"}),
        ):
            versioncheck.checkGithub()

        info = system_service.get_version_info(ctx)
        assert info["update_state"] == "current"
        assert info["latest_version"] == "0.20.0"

    def test_ahead_collapses_to_current(self, ctx):
        with (
            patch.object(system_service, "get_release_version", return_value="0.22.0"),
            patch.object(versioncheck, "get_release_version", return_value="0.22.0"),
            patch.object(
                versioncheck.requests,
                "get",
                return_value=_github_response({"tag_name": "v0.20.0"}),
            ),
        ):
            versioncheck.checkGithub()

        assert system_service.get_version_info(ctx)["update_state"] == "current"

    def test_strips_leading_v_once(self, ctx):
        with patch.object(
            versioncheck.requests,
            "get",
            return_value=_github_response({"tag_name": "v0.21.0"}),
        ):
            versioncheck.checkGithub()

        assert system_service.get_version_info(ctx)["latest_version"] == "0.21.0"
        assert not system_service.get_version_info(ctx)["latest_version"].startswith("v")

    def test_unparseable_remote_is_unknown_not_current(self, ctx):
        with patch.object(
            versioncheck.requests,
            "get",
            return_value=_github_response({"tag_name": "not-a-version"}),
        ):
            versioncheck.checkGithub()

        info = system_service.get_version_info(ctx)
        assert info["update_state"] == "unknown"
        assert info["update_state"] != "current"
        # Failed check after contact — never rewrite as never_checked.
        assert info["update_reason"] == "unreachable"

    def test_unreachable_sets_reason(self, ctx):
        with patch.object(versioncheck.requests, "get", side_effect=RuntimeError("no network")):
            versioncheck.checkGithub()

        info = system_service.get_version_info(ctx)
        assert info["update_state"] == "unknown"
        assert info["update_reason"] == "unreachable"

    def test_rate_limited_sets_reason(self, ctx):
        with patch.object(
            versioncheck.requests,
            "get",
            return_value=_github_response(
                {"message": "API rate limit exceeded"},
                status_code=403,
                headers={"X-RateLimit-Remaining": "0"},
            ),
        ):
            versioncheck.checkGithub()

        info = system_service.get_version_info(ctx)
        assert info["update_state"] == "unknown"
        assert info["update_reason"] == "rate_limited"

    def test_http_429_is_rate_limited(self, ctx):
        with patch.object(
            versioncheck.requests,
            "get",
            return_value=_github_response({"message": "rate limited"}, status_code=429),
        ):
            versioncheck.checkGithub()

        info = system_service.get_version_info(ctx)
        assert info["update_state"] == "unknown"
        assert info["update_reason"] == "rate_limited"

    def test_never_checked_before_first_run(self, ctx):
        info = system_service.get_version_info(ctx)
        assert info["update_state"] == "unknown"
        assert info["update_reason"] == "never_checked"

    def test_failure_never_reports_current(self, ctx):
        with patch.object(
            versioncheck.requests,
            "get",
            return_value=_github_response({"tag_name": "v0.21.0"}),
        ):
            versioncheck.checkGithub()
        assert system_service.get_version_info(ctx)["update_state"] == "behind"

        with patch.object(versioncheck.requests, "get", side_effect=RuntimeError("outage")):
            versioncheck.checkGithub()

        info = system_service.get_version_info(ctx)
        assert info["update_state"] == "unknown"
        assert info["update_state"] != "current"
        assert info["update_reason"] == "unreachable"

    def test_does_not_write_check_update_global_messages(self, ctx):
        with patch.object(
            versioncheck.requests,
            "get",
            return_value=_github_response({"tag_name": "v0.21.0"}),
        ):
            result = versioncheck.checkGithub()

        assert comicarr.GLOBAL_MESSAGES is None
        assert result is None or result.get("event") != "check_update"

    def test_timeout_on_every_request(self, ctx):
        with patch.object(
            versioncheck.requests,
            "get",
            return_value=_github_response({"tag_name": "v0.20.0"}),
        ) as mock_get:
            versioncheck.checkGithub()

        assert mock_get.call_count == 1
        assert mock_get.call_args.kwargs.get("timeout") == versioncheck._GITHUB_REQUEST_TIMEOUT
        assert versioncheck._GITHUB_REQUEST_TIMEOUT == (10, 10)

    def test_preserves_auth_with_timeout(self, ctx):
        token = ("ghp_test", "x-oauth-basic")
        comicarr.CONFIG.GIT_TOKEN = token
        with patch.object(
            versioncheck.requests,
            "get",
            return_value=_github_response({"tag_name": "v0.20.0"}),
        ) as mock_get:
            versioncheck.checkGithub()

        assert mock_get.call_args.kwargs.get("auth") is token
        assert mock_get.call_args.kwargs.get("timeout") == (10, 10)

    def test_timeout_error_is_unreachable(self, ctx):
        with patch.object(
            versioncheck.requests,
            "get",
            side_effect=versioncheck.requests.exceptions.Timeout("connect timed out"),
        ):
            versioncheck.checkGithub()

        info = system_service.get_version_info(ctx)
        assert info["update_state"] == "unknown"
        assert info["update_reason"] == "unreachable"

    def test_legacy_globals_stay_in_step(self, ctx):
        with patch.object(
            versioncheck.requests,
            "get",
            return_value=_github_response({"tag_name": "v0.21.0"}),
        ):
            versioncheck.checkGithub()

        assert comicarr.LATEST_VERSION == "0.21.0"
        assert ctx.latest_version == comicarr.LATEST_VERSION
        assert ctx.update_state == "behind"


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


class TestCheckGithubMigration:
    def test_false_becomes_true_when_upgrading_to_sixteen(self):
        from comicarr.config import apply_check_github_v16_migration

        assert apply_check_github_v16_migration(old_version=15, check_github=False) is True

    def test_true_stays_true(self):
        from comicarr.config import apply_check_github_v16_migration

        assert apply_check_github_v16_migration(old_version=15, check_github=True) is True

    def test_already_at_sixteen_is_left_alone(self):
        from comicarr.config import apply_check_github_v16_migration

        assert apply_check_github_v16_migration(old_version=16, check_github=False) is False


class TestDeadToastPathAbsent:
    def test_use_server_events_has_no_check_update_listener(self):
        from pathlib import Path

        text = Path("frontend/src/hooks/useServerEvents.ts").read_text()
        assert "check_update" not in text
        assert "CheckUpdateEventData" not in text

    def test_events_types_drop_check_update(self):
        from pathlib import Path

        text = Path("frontend/src/types/events.ts").read_text()
        assert "CheckUpdateEventData" not in text
        assert "check_update" not in text
