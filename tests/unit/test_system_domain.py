"""
Tests for comicarr.app.system domain — Phase 1.

Covers: auth login/logout, SSE streaming, config endpoints, JWT cookies.
"""

import configparser
import datetime
import json
import os
import stat
import threading
from unittest.mock import MagicMock, patch

import pytest

import comicarr

# Ensure LOG_LEVEL is set for tests (logger.info checks LOG_LEVEL > 0)
if comicarr.LOG_LEVEL is None:
    comicarr.LOG_LEVEL = 0

from comicarr.app.core.context import AppContext
from comicarr.app.core.security import (
    create_session_token,
    validate_jwt_token,
)
from comicarr.app.system import router as system_router
from comicarr.app.system import service as system_service


def _make_test_ctx(**overrides):
    """Create a test AppContext for system domain tests."""
    config = MagicMock()
    config.HTTP_USERNAME = "admin"
    config.HTTP_PASSWORD = "$2b$12$LJ3m4ys5Cq2n5o/xBp6Mj.abcdefghijklmnopqrstuv"  # bcrypt hash
    config.ENABLE_HTTPS = False
    config.API_KEY = "configured-api-key"
    config.COMICVINE_API = "configured-comicvine-key"
    config.AI_API_KEY = None
    config.METRON_PASSWORD = None
    config.MAL_CLIENT_ID = None
    config.PROWL_KEYS = "configured-prowl-keys"
    config.SLACK_WEBHOOK_URL = "configured-slack-webhook"
    config.MATTERMOST_WEBHOOK_URL = "configured-mattermost-webhook"
    config.DISCORD_WEBHOOK_URL = "configured-discord-webhook"
    config.SECURE_DIR = "/tmp/test_secure"
    config.OPDS_USERNAME = None
    config.OPDS_PASSWORD = None
    config.LOGIN_TIMEOUT = 43800
    config.COMIC_DIR = "/comics"
    config.DESTINATION_DIR = "/downloads"
    config.LOG_DIR = None

    def process_kwargs(values):
        for key, value in values.items():
            setattr(config, key.upper(), value)

    config.process_kwargs.side_effect = process_kwargs

    def apply_transaction(values, configure=True):
        previous = {key.upper(): getattr(config, key.upper(), None) for key in values}
        try:
            config.process_kwargs(values)
            if configure:
                config.configure(update=True, startup=False)
            return True
        except Exception:
            for key, value in previous.items():
                setattr(config, key, value)
            return False

    config.apply_transaction.side_effect = apply_transaction

    defaults = {
        "config": config,
        "jwt_secret_key": b"test_secret_key_32_bytes_padding!",
        "jwt_generation": 0,
        "sse_key": "test_sse_key",
        "download_apikey": "test_dl_key",
        "scheduler": MagicMock(),
        "setup_token": None,
    }
    defaults.update(overrides)
    return AppContext(**defaults)


# =============================================================================
# Login Service Tests
# =============================================================================


class TestVerifyLogin:
    @patch("comicarr.encrypted")
    def test_successful_bcrypt_login(self, mock_encrypted):
        """Login with correct bcrypt password succeeds."""
        ctx = _make_test_ctx()
        mock_encrypted.verify_password.return_value = True

        result = system_service.verify_login(ctx, "admin", "correct_password", "127.0.0.1")
        assert result["success"] is True
        assert result["username"] == "admin"

    @patch("comicarr.encrypted")
    def test_wrong_password_fails(self, mock_encrypted):
        """Login with wrong password fails."""
        ctx = _make_test_ctx()
        mock_encrypted.verify_password.return_value = False

        result = system_service.verify_login(ctx, "admin", "wrong_password", "127.0.0.1")
        assert result["success"] is False
        assert "error" in result

    def test_wrong_username_fails(self):
        """Login with wrong username fails."""
        ctx = _make_test_ctx()

        result = system_service.verify_login(ctx, "hacker", "any_password", "127.0.0.1")
        assert result["success"] is False

    def test_rate_limiting_blocks_after_5_failures(self):
        """Rate limiter blocks after 5 failed attempts."""
        ctx = _make_test_ctx()

        # Simulate 5 failed logins from same IP
        for _ in range(5):
            system_service.verify_login(ctx, "wrong_user", "wrong_pass", "10.0.0.99")

        # 6th attempt should be blocked
        result = system_service.verify_login(ctx, "admin", "any", "10.0.0.99")
        assert result["success"] is False
        assert "Incorrect" in result["error"]

    def test_no_config_returns_error(self):
        """Login without configured auth returns error."""
        ctx = _make_test_ctx()
        ctx.config.HTTP_USERNAME = None
        ctx.config.HTTP_PASSWORD = None

        result = system_service.verify_login(ctx, "admin", "pass", "127.0.0.1")
        assert result["success"] is False

    @patch("comicarr.encrypted")
    def test_password_migration_uses_shared_transaction_without_configure(self, mock_encrypted):
        """Login hash migration does not mutate the parser outside the transaction lock."""
        ctx = _make_test_ctx()
        mock_encrypted.hash_password.return_value = "$2b$12$migrated"

        system_service._migrate_password(ctx, "legacy-password")

        ctx.config.apply_transaction.assert_called_once_with({"http_password": "$2b$12$migrated"}, configure=False)
        ctx.config.writeconfig.assert_not_called()

    @patch("comicarr.encrypted")
    def test_password_migration_failure_is_logged_and_non_raising(self, mock_encrypted):
        """Failed bcrypt migration must not raise out of the migration helper."""
        ctx = _make_test_ctx()
        mock_encrypted.hash_password.return_value = "$2b$12$migrated"
        ctx.config.apply_transaction.side_effect = None
        ctx.config.apply_transaction.return_value = False

        system_service._migrate_password(ctx, "legacy-password")

        ctx.config.apply_transaction.assert_called_once_with({"http_password": "$2b$12$migrated"}, configure=False)

    @patch("comicarr.encrypted")
    def test_plaintext_login_succeeds_when_password_migration_fails(self, mock_encrypted):
        """Login still succeeds if hash migration cannot be persisted."""
        ctx = _make_test_ctx()
        ctx.config.HTTP_PASSWORD = "legacy-password"
        mock_encrypted.hash_password.return_value = "$2b$12$migrated"
        ctx.config.apply_transaction.side_effect = None
        ctx.config.apply_transaction.return_value = False

        result = system_service.verify_login(ctx, "admin", "legacy-password", "127.0.0.1")

        assert result["success"] is True
        assert result["username"] == "admin"
        assert ctx.config.HTTP_PASSWORD == "legacy-password"
        ctx.config.apply_transaction.assert_called_once_with({"http_password": "$2b$12$migrated"}, configure=False)


# =============================================================================
# JWT Token Integration Tests
# =============================================================================


class TestJWTIntegration:
    def test_login_produces_valid_jwt(self):
        """A successful login should produce a JWT that validates."""
        secret = b"test_secret_key_32_bytes_padding!"
        token = create_session_token("admin", secret, generation=0)
        username = validate_jwt_token(token, secret, current_generation=0)
        assert username == "admin"

    def test_revoked_generation_invalidates_token(self):
        """Incrementing jwt_generation invalidates all tokens."""
        secret = b"test_secret_key_32_bytes_padding!"
        token = create_session_token("admin", secret, generation=0)

        # Token valid with generation 0
        assert validate_jwt_token(token, secret, 0) == "admin"
        # Token invalid after generation bump (simulating revocation)
        assert validate_jwt_token(token, secret, 1) is None


# =============================================================================
# Initial Setup Tests
# =============================================================================


class TestAnnounceSetupToken:
    def test_quiet_mode_prints_token_and_logs(self, monkeypatch, capsys):
        """Quiet mode still prints the setup token to container stdout."""
        expected = [
            "[SETUP] *** First-run setup required ***",
            "[SETUP] Setup token: secret-token",
            "[SETUP] Provide this token when setting up credentials via the web interface.",
        ]
        monkeypatch.setattr(comicarr, "QUIET", True)
        monkeypatch.setattr(comicarr, "LOG_LEVEL", 1)

        with patch.object(system_service.logger, "info") as mock_info:
            system_service.announce_setup_token("secret-token")

        captured = capsys.readouterr()
        assert captured.out.splitlines() == expected
        assert [call.args[0] for call in mock_info.call_args_list] == expected

    def test_normal_mode_logs_without_stdout_duplicate(self, monkeypatch, capsys):
        """Normal logging mode relies on the configured logger only."""
        expected = [
            "[SETUP] *** First-run setup required ***",
            "[SETUP] Setup token: secret-token",
            "[SETUP] Provide this token when setting up credentials via the web interface.",
        ]
        monkeypatch.setattr(comicarr, "QUIET", False)
        monkeypatch.setattr(comicarr, "LOG_LEVEL", 1)

        with patch.object(system_service.logger, "info") as mock_info:
            system_service.announce_setup_token("secret-token")

        captured = capsys.readouterr()
        assert captured.out == ""
        assert [call.args[0] for call in mock_info.call_args_list] == expected

    def test_log_level_zero_prints_token_even_when_not_quiet(self, monkeypatch, capsys):
        """Console-suppressed log level still exposes the setup token."""
        expected = [
            "[SETUP] *** First-run setup required ***",
            "[SETUP] Setup token: secret-token",
            "[SETUP] Provide this token when setting up credentials via the web interface.",
        ]
        monkeypatch.setattr(comicarr, "QUIET", False)
        monkeypatch.setattr(comicarr, "LOG_LEVEL", 0)

        with patch.object(system_service.logger, "info") as mock_info:
            system_service.announce_setup_token("secret-token")

        captured = capsys.readouterr()
        assert captured.out.splitlines() == expected
        assert [call.args[0] for call in mock_info.call_args_list] == expected


class TestInitialSetup:
    @patch("comicarr.encrypted")
    def test_setup_succeeds(self, mock_encrypted):
        """Initial setup with valid credentials succeeds."""
        ctx = _make_test_ctx()
        ctx.config.HTTP_USERNAME = None
        ctx.config.HTTP_PASSWORD = None
        mock_encrypted.hash_password.return_value = "$2b$12$hashed"

        # initial_setup does `import comicarr` locally and sets globals —
        # this is harmless in tests, just let it run
        result = system_service.initial_setup(ctx, "admin", "password123", None)
        assert result["success"] is True
        ctx.config.apply_transaction.assert_called_once_with(
            {
                "http_username": "admin",
                "http_password": "$2b$12$hashed",
                "authentication": 2,
            }
        )

    @patch("comicarr.encrypted")
    def test_setup_persistence_failure_preserves_setup_state(self, mock_encrypted, monkeypatch):
        """Failed setup writes must leave credentials, tokens, and signals unchanged."""
        ctx = _make_test_ctx(setup_token="setup-token")
        ctx.config.HTTP_USERNAME = None
        ctx.config.HTTP_PASSWORD = None
        ctx.config.apply_transaction.side_effect = None
        ctx.config.apply_transaction.return_value = False
        mock_encrypted.hash_password.return_value = "$2b$12$hashed"
        monkeypatch.setattr(comicarr, "SETUP_TOKEN", "setup-token")
        monkeypatch.setattr(comicarr, "SIGNAL", None)

        result = system_service.initial_setup(ctx, "admin", "password123", "setup-token")

        assert result == {"success": False, "error": "Failed to persist initial credentials"}
        assert ctx.config.HTTP_USERNAME is None
        assert ctx.config.HTTP_PASSWORD is None
        assert ctx.setup_token == "setup-token"
        assert comicarr.SETUP_TOKEN == "setup-token"
        assert ctx.signal is None
        assert comicarr.SIGNAL is None

    @patch("comicarr.encrypted")
    def test_setup_hash_failure_preserves_setup_state(self, mock_encrypted, monkeypatch):
        """Password hashing failures use the controlled setup persistence contract."""
        ctx = _make_test_ctx(setup_token="setup-token")
        ctx.config.HTTP_USERNAME = None
        ctx.config.HTTP_PASSWORD = None
        mock_encrypted.hash_password.side_effect = RuntimeError("hash failed")
        monkeypatch.setattr(comicarr, "SETUP_TOKEN", "setup-token")
        monkeypatch.setattr(comicarr, "SIGNAL", None)

        result = system_service.initial_setup(ctx, "admin", "password123", "setup-token")

        assert result == {"success": False, "error": "Failed to persist initial credentials"}
        ctx.config.apply_transaction.assert_not_called()
        assert ctx.setup_token == "setup-token"
        assert comicarr.SETUP_TOKEN == "setup-token"
        assert ctx.signal is None
        assert comicarr.SIGNAL is None

    def test_setup_rejects_short_password(self):
        """Setup rejects passwords shorter than 8 characters."""
        ctx = _make_test_ctx()
        ctx.config.HTTP_USERNAME = None
        ctx.config.HTTP_PASSWORD = None

        result = system_service.initial_setup(ctx, "admin", "short", None)
        assert result["success"] is False
        assert "8 characters" in result["error"]

    def test_setup_rejects_when_already_configured(self):
        """Setup fails if credentials are already set."""
        ctx = _make_test_ctx()
        # config.HTTP_USERNAME and HTTP_PASSWORD are already set

        result = system_service.initial_setup(ctx, "admin", "password123", None)
        assert result["success"] is False
        assert "already configured" in result["error"]

    def test_setup_validates_token(self):
        """Setup requires valid setup token when one is active."""
        ctx = _make_test_ctx(setup_token="correct_token")
        ctx.config.HTTP_USERNAME = None
        ctx.config.HTTP_PASSWORD = None

        result = system_service.initial_setup(ctx, "admin", "password123", "wrong_token")
        assert result["success"] is False
        assert "Invalid setup token" in result["error"]


# =============================================================================
# Config Service Tests
# =============================================================================


class TestConfigService:
    def test_get_safe_config_returns_lowercase_keys(self):
        """get_safe_config returns all keys in lowercase."""
        ctx = _make_test_ctx()
        ctx.config.COMIC_DIR = "/my/comics"
        ctx.config.HTTP_PORT = 8090

        result = system_service.get_safe_config(ctx)
        assert "comic_dir" in result
        assert "http_port" in result
        # All keys should be lowercase
        for key in result:
            assert key == key.lower(), "Key %s should be lowercase" % key

    def test_get_safe_config_excludes_passwords(self):
        """get_safe_config returns config without sensitive fields."""
        ctx = _make_test_ctx()
        ctx.config.COMIC_DIR = "/my/comics"
        ctx.config.HTTP_PORT = 8090

        result = system_service.get_safe_config(ctx)
        assert "comic_dir" in result
        assert "http_port" in result
        # Passwords should not be present (check both cases)
        assert "http_password" not in result
        assert "HTTP_PASSWORD" not in result

    def test_get_safe_config_redacts_long_lived_secrets(self):
        """get_safe_config exposes secret indicators without secret values."""
        ctx = _make_test_ctx()
        result = system_service.get_safe_config(ctx)

        redacted_keys = [
            "api_key",
            "comicvine_api",
            "prowl_keys",
            "slack_webhook_url",
            "mattermost_webhook_url",
            "discord_webhook_url",
        ]
        for key in redacted_keys:
            assert key not in result

        assert result["api_key_set"] is True
        assert result["comicvine_api_set"] is True
        assert result["prowl_keys_set"] is True
        assert result["slack_webhook_url_set"] is True
        assert result["mattermost_webhook_url_set"] is True
        assert result["discord_webhook_url_set"] is True

    def test_get_safe_config_secret_indicators_false_when_empty(self):
        """Secret indicators are False when existing config values are empty."""
        ctx = _make_test_ctx()
        ctx.config.API_KEY = ""
        ctx.config.COMICVINE_API = "None"
        ctx.config.PROWL_KEYS = None
        ctx.config.SLACK_WEBHOOK_URL = ""
        ctx.config.MATTERMOST_WEBHOOK_URL = "None"
        ctx.config.DISCORD_WEBHOOK_URL = None

        result = system_service.get_safe_config(ctx)

        assert result["api_key_set"] is False
        assert result["comicvine_api_set"] is False
        assert result["prowl_keys_set"] is False
        assert result["slack_webhook_url_set"] is False
        assert result["mattermost_webhook_url_set"] is False
        assert result["discord_webhook_url_set"] is False

    def test_get_safe_config_includes_new_keys(self):
        """get_safe_config includes all frontend-needed keys."""
        ctx = _make_test_ctx()
        ctx.config.COMICVINE_ENABLED = True
        ctx.config.MANGADEX_ENABLED = False
        ctx.config.PREFERRED_QUALITY = "high"

        result = system_service.get_safe_config(ctx)
        assert "comicvine_enabled" in result
        assert "mangadex_enabled" in result
        assert "preferred_quality" in result

    def test_get_safe_config_includes_metron_password_set_indicator(self):
        """get_safe_config returns metron_password_set boolean, not the actual password."""
        ctx = _make_test_ctx()
        ctx.config.METRON_PASSWORD = "gAAAAAsecretencrypted"
        result = system_service.get_safe_config(ctx)
        assert result["metron_password_set"] is True
        assert "metron_password" not in result

    def test_get_safe_config_metron_password_set_false_when_empty(self):
        """metron_password_set is False when no password is configured."""
        ctx = _make_test_ctx()
        ctx.config.METRON_PASSWORD = None
        result = system_service.get_safe_config(ctx)
        assert result["metron_password_set"] is False

    def test_get_safe_config_includes_download_client_labels(self):
        """get_safe_config returns derived download client labels matching config.py enums."""
        ctx = _make_test_ctx()
        ctx.config.NZB_DOWNLOADER = 0
        ctx.config.TORRENT_DOWNLOADER = 1
        result = system_service.get_safe_config(ctx)
        assert result["nzb_downloader_label"] == "SABnzbd"
        assert result["torrent_downloader_label"] == "uTorrent"

    def test_get_safe_config_download_labels_all_values(self):
        """Verify all download client enum values map to correct labels."""
        ctx = _make_test_ctx()
        # NZB: 0=SABnzbd, 1=NZBGet, 2=Blackhole, 3=Disabled
        for val, label in [(0, "SABnzbd"), (1, "NZBGet"), (2, "Blackhole"), (3, "Disabled")]:
            ctx.config.NZB_DOWNLOADER = val
            result = system_service.get_safe_config(ctx)
            assert result["nzb_downloader_label"] == label, "NZB %d should be %s" % (val, label)
        # Torrent: 0=Watchfolder, 1=uTorrent, 2=rTorrent, 3=Transmission, 4=Deluge, 5=qBittorrent
        for val, label in [
            (0, "Watchfolder"),
            (1, "uTorrent"),
            (2, "rTorrent"),
            (3, "Transmission"),
            (4, "Deluge"),
            (5, "qBittorrent"),
        ]:
            ctx.config.TORRENT_DOWNLOADER = val
            result = system_service.get_safe_config(ctx)
            assert result["torrent_downloader_label"] == label, "Torrent %d should be %s" % (val, label)

    def test_get_safe_config_unknown_downloader_value(self):
        """Unknown downloader enum values fall back to 'None' string."""
        ctx = _make_test_ctx()
        ctx.config.NZB_DOWNLOADER = 99
        result = system_service.get_safe_config(ctx)
        assert result["nzb_downloader_label"] == "None"

    def test_get_safe_config_includes_version_from_context(self):
        """get_safe_config includes version when ctx.current_version is set."""
        ctx = _make_test_ctx(current_version="1.2.3")
        result = system_service.get_safe_config(ctx)
        assert result["version"] == "1.2.3"

    @patch("importlib.metadata.version", return_value="0.8.0")
    def test_get_safe_config_falls_back_to_importlib_metadata(self, mock_version):
        """get_safe_config falls back to importlib.metadata when ctx.current_version is None."""
        ctx = _make_test_ctx(current_version=None)
        result = system_service.get_safe_config(ctx)
        assert result["version"] == "0.8.0"
        mock_version.assert_called_once_with("comicarr")

    @patch("importlib.metadata.version", side_effect=Exception("not found"))
    @patch("pathlib.Path.is_file", return_value=False)
    def test_get_safe_config_omits_version_when_unavailable(self, mock_isfile, mock_version):
        """get_safe_config omits version key when all sources fail."""
        ctx = _make_test_ctx(current_version=None)
        result = system_service.get_safe_config(ctx)
        assert "version" not in result

    def test_update_config_accepts_lowercase_keys(self):
        """update_config normalizes lowercase keys to uppercase."""
        ctx = _make_test_ctx()
        result = system_service.update_config(ctx, {"comic_dir": "/new/path"})
        assert result["success"] is True
        ctx.config.apply_transaction.assert_called_once()
        args = ctx.config.apply_transaction.call_args[0][0]
        assert "COMIC_DIR" in args

    def test_update_config_accepts_uppercase_keys(self):
        """update_config still accepts uppercase keys (backward compat)."""
        ctx = _make_test_ctx()
        result = system_service.update_config(ctx, {"COMIC_DIR": "/new/path"})
        assert result["success"] is True

    def test_update_config_rejects_sensitive_keys_regardless_of_case(self):
        """update_config rejects api_key, http_password in any casing."""
        ctx = _make_test_ctx()
        result = system_service.update_config(ctx, {"api_key": "hacked", "http_password": "hacked"})
        assert result["success"] is False
        assert "No valid config keys" in result["error"]

    def test_update_config_filters_sensitive_keys_from_mixed_payload(self):
        """update_config applies valid keys and silently filters sensitive ones."""
        ctx = _make_test_ctx()
        result = system_service.update_config(
            ctx,
            {
                "comic_dir": "/new/path",
                "api_key": "hacked",
            },
        )
        assert result["success"] is True
        args = ctx.config.apply_transaction.call_args[0][0]
        assert "COMIC_DIR" in args
        assert "API_KEY" not in args

    def test_update_config_reports_persistence_failure_without_side_effects(self, monkeypatch):
        """Failed durable writes must not reconfigure schedulers or replace the global config."""
        ctx = _make_test_ctx()
        previous_global = object()
        monkeypatch.setattr(comicarr, "CONFIG", previous_global)
        ctx.config.apply_transaction.side_effect = None
        ctx.config.apply_transaction.return_value = False

        with patch.object(system_service, "_reconfigure_schedulers") as reconfigure:
            result = system_service.update_config(ctx, {"search_interval": 720})

        assert result == {"success": False, "error": "Failed to persist configuration"}
        reconfigure.assert_not_called()
        assert comicarr.CONFIG is previous_global

    def test_update_config_reconfigures_scheduler_after_persistence(self):
        """Scheduler changes happen only after the transactional write succeeds."""
        ctx = _make_test_ctx()
        events = []

        def persist(values):
            events.append("persist")
            return True

        ctx.config.apply_transaction.side_effect = persist
        with patch.object(
            system_service, "_reconfigure_schedulers", side_effect=lambda _ctx: events.append("scheduler")
        ):
            result = system_service.update_config(ctx, {"search_interval": 720})

        assert result == {"success": True}
        assert events == ["persist", "scheduler"]

    @patch("comicarr.app.system.service.secrets.token_hex", return_value="a" * 32)
    def test_regenerate_api_key_persists_new_key(self, mock_token_hex):
        """regenerate_api_key creates, persists, and returns a server-side key."""
        ctx = _make_test_ctx()
        result = system_service.regenerate_api_key(ctx)

        assert result == {"success": True, "api_key": "a" * 32}
        assert ctx.config.API_KEY == "a" * 32
        mock_token_hex.assert_called_once_with(16)
        ctx.config.apply_transaction.assert_called_once_with({"api_key": "a" * 32})
        ctx.config.writeconfig.assert_not_called()
        ctx.config.configure.assert_called_once_with(update=True, startup=False)

    def test_regenerate_api_key_rejects_missing_config(self):
        """regenerate_api_key fails when config is not loaded."""
        ctx = _make_test_ctx(config=None)
        result = system_service.regenerate_api_key(ctx)
        assert result["success"] is False
        assert result["error"] == "Config not loaded"

    @patch("comicarr.app.system.service.secrets.token_hex", return_value="a" * 32)
    def test_regenerate_api_key_reports_persistence_failure(self, mock_token_hex):
        """regenerate_api_key reports persistence failures through the result contract."""
        ctx = _make_test_ctx()
        ctx.config.configure.side_effect = RuntimeError("cannot reload")

        result = system_service.regenerate_api_key(ctx)

        assert result == {"success": False, "error": "Failed to persist new API key"}
        assert ctx.config.API_KEY == "configured-api-key"
        mock_token_hex.assert_called_once_with(16)
        ctx.config.apply_transaction.assert_called_once_with({"api_key": "a" * 32})
        ctx.config.writeconfig.assert_not_called()
        ctx.config.configure.assert_called_once_with(update=True, startup=False)

    @patch("comicarr.app.system.service.secrets.token_hex", return_value="a" * 32)
    def test_regenerate_api_key_reports_transaction_failure(self, mock_token_hex):
        """regenerate_api_key fails when the transactional write is unsuccessful."""
        ctx = _make_test_ctx()
        ctx.config.apply_transaction.side_effect = None
        ctx.config.apply_transaction.return_value = False

        result = system_service.regenerate_api_key(ctx)

        assert result == {"success": False, "error": "Failed to persist new API key"}
        assert ctx.config.API_KEY == "configured-api-key"
        mock_token_hex.assert_called_once_with(16)
        ctx.config.apply_transaction.assert_called_once_with({"api_key": "a" * 32})
        ctx.config.writeconfig.assert_not_called()
        ctx.config.configure.assert_not_called()

    def test_update_config_accepts_new_writable_keys(self):
        """update_config accepts newly added writable keys."""
        ctx = _make_test_ctx()
        result = system_service.update_config(
            ctx,
            {
                "comicvine_enabled": True,
                "preferred_quality": "high",
                "use_minsize": True,
                "minsize": 50,
            },
        )
        assert result["success"] is True
        args = ctx.config.apply_transaction.call_args[0][0]
        assert "COMICVINE_ENABLED" in args
        assert "PREFERRED_QUALITY" in args

    def test_get_job_info(self):
        """get_job_info returns scheduler job list."""
        ctx = _make_test_ctx()
        mock_job = MagicMock()
        mock_job.id = "search_job"
        mock_job.name = "Search"
        mock_job.next_run_time = None
        mock_job.trigger = "interval"
        ctx.scheduler.get_jobs.return_value = [mock_job]

        result = system_service.get_job_info(ctx)
        assert len(result["jobs"]) == 1
        assert result["jobs"][0]["id"] == "search_job"

    def test_get_job_info_includes_durable_weekly_outcomes(self):
        """The weekly scheduler reports its durable outcome fields for refresh polling."""
        ctx = _make_test_ctx()
        mock_job = MagicMock()
        mock_job.id = "weekly"
        mock_job.name = "Weekly Pullist"
        mock_job.next_run_time = "2026-07-12T00:00:00Z"
        mock_job.trigger = "interval"
        ctx.scheduler.get_jobs.return_value = [mock_job]

        with patch.object(
            system_service,
            "_get_weekly_job_history",
            return_value={
                "status": "Error",
                "last_success_timestamp": 100.0,
                "last_failure_timestamp": 200.0,
                "last_error": "upstream unavailable",
            },
        ):
            result = system_service.get_job_info(ctx)

        weekly = result["jobs"][0]
        assert weekly["state"] == "error"
        assert weekly["last_success_timestamp"] == 100.0
        assert weekly["last_failure_timestamp"] == 200.0
        assert weekly["last_error"] == "upstream unavailable"

    def test_weekly_refresh_queues_the_existing_scheduler_job(self, monkeypatch):
        """Manual refresh modifies the existing weekly job instead of creating work."""
        ctx = _make_test_ctx()
        job = MagicMock()
        job.next_run_time = datetime.datetime(2026, 7, 12, 0, 0, 0)
        ctx.scheduler.get_job.return_value = job
        monkeypatch.setattr(comicarr, "WEEKLY_STATUS", "Waiting")
        monkeypatch.setattr(comicarr, "WEEKLY_MANUAL_NEXT_RUN", None)

        with patch.object(system_service.db, "upsert") as upsert:
            result = system_service.request_weekly_refresh(ctx)

        assert result["accepted"] is True
        assert result["state"] == "queued"
        job.modify.assert_called_once()
        upsert.assert_called_once_with("jobhistory", {"status": "Queued"}, {"JobName": "Weekly Pullist"})
        assert comicarr.WEEKLY_MANUAL_NEXT_RUN == job.next_run_time

    def test_weekly_refresh_coalesces_an_already_queued_request(self, monkeypatch):
        """Repeated clicks leave one scheduled run in place."""
        ctx = _make_test_ctx()
        job = MagicMock()
        job.next_run_time = "2026-07-12T00:00:00Z"
        ctx.scheduler.get_job.return_value = job
        monkeypatch.setattr(comicarr, "WEEKLY_STATUS", "Queued")

        result = system_service.request_weekly_refresh(ctx)

        assert result == {
            "accepted": False,
            "state": "queued",
            "next_run_time": "2026-07-12T00:00:00Z",
        }
        job.modify.assert_not_called()

    def test_weekly_refresh_rejects_while_the_job_is_running(self, monkeypatch):
        """A running weekly pull cannot be scheduled a second time."""
        ctx = _make_test_ctx()
        job = MagicMock()
        job.next_run_time = "2026-07-12T00:00:00Z"
        ctx.scheduler.get_job.return_value = job
        monkeypatch.setattr(comicarr, "WEEKLY_STATUS", "Running")

        result = system_service.request_weekly_refresh(ctx)

        assert result["accepted"] is False
        assert result["state"] == "running"
        job.modify.assert_not_called()

    def test_weekly_completion_preserves_the_scheduler_next_run(self, monkeypatch):
        """A manual pull does not replace APScheduler's interval cadence."""
        next_run = datetime.datetime(2026, 7, 10, 16, 0, 0)

        class WeeklyJob:
            next_run_time = next_run

            def __init__(self):
                self.modify_calls = 0

            def __str__(self):
                return "Weekly Pullist (trigger: interval], next run at: 2026-07-10 16:00:00 UTC)"

            def modify(self, **_kwargs):
                self.modify_calls += 1

        job = WeeklyJob()
        scheduler = MagicMock()
        scheduler.get_jobs.return_value = [job]
        monkeypatch.setattr(comicarr, "SCHED", scheduler)
        monkeypatch.setattr(comicarr, "WEEKLY_STATUS", "Waiting")
        monkeypatch.setattr(comicarr, "SCHED_WEEKLY_LAST", None)
        monkeypatch.setattr(comicarr, "FORCE_STATUS", {})

        with patch.object(system_service.db, "upsert") as upsert:
            system_service.job_management(
                write=True,
                job="Weekly Pullist",
                last_run_completed=1_783_692_000.0,
                status="Waiting",
            )

        assert job.modify_calls == 0
        values = upsert.call_args.args[1]
        assert values["next_run_datetime"] == next_run
        assert values["next_run_timestamp"] == next_run.timestamp()

    def test_startup_recovers_an_interrupted_weekly_refresh(self, monkeypatch):
        """A persisted Running state becomes safe-to-schedule after a restart."""
        monkeypatch.setattr(comicarr, "SCHED_WEEKLY_LAST", None)
        monkeypatch.setattr(comicarr, "WEEKLY_STATUS", "Waiting")
        monkeypatch.setattr(
            system_service.db,
            "select_all",
            lambda statement: [
                {
                    "JobName": "Weekly Pullist",
                    "status": "Running",
                    "prev_run_timestamp": 200.0,
                    "last_success_timestamp": 100.0,
                }
            ],
        )

        with patch.object(system_service.db, "upsert") as upsert:
            result = system_service.job_management(startup=True)

        assert result["weekly"] == {"last": 100.0, "status": "Waiting"}
        upsert.assert_called_once_with(
            "jobhistory",
            {
                "status": "Waiting",
                "last_failure_timestamp": 200.0,
                "last_error": "Previous weekly refresh was interrupted by restart.",
            },
            {"JobName": "Weekly Pullist"},
        )

    def test_sanitize_job_error_redacts_credentials(self):
        message = system_service.sanitize_job_error("token=secret https://user:pass@example.test failed")

        assert "secret" not in message
        assert "user:pass" not in message
        assert "[redacted]" in message

    def test_get_version_info(self):
        """get_version_info returns version data from context."""
        ctx = _make_test_ctx(current_version="0.6.0", install_type="git")

        result = system_service.get_version_info(ctx)
        assert result["current_version"] == "0.6.0"
        assert result["install_type"] == "git"


class _JsonRequest:
    def __init__(self, body):
        self._body = body

    async def json(self):
        return self._body


class TestConfigRouter:
    @pytest.mark.asyncio
    async def test_setup_returns_server_error_when_persistence_fails(self):
        """The setup endpoint distinguishes storage failure from invalid input."""
        ctx = _make_test_ctx(setup_token="setup-token")
        failure = {"success": False, "error": "Failed to persist initial credentials"}
        request = _JsonRequest(
            {
                "username": "admin",
                "password": "password123",
                "setup_token": "setup-token",
            }
        )

        with patch.object(system_router.system_service, "initial_setup", return_value=failure):
            response = await system_router.setup(request, ctx)

        assert response.status_code == 500
        assert json.loads(response.body) == failure

    @pytest.mark.asyncio
    async def test_setup_returns_bad_request_for_validation_failure(self):
        """Client-input failures remain HTTP 400, not 500."""
        ctx = _make_test_ctx(setup_token="setup-token")
        failure = {"success": False, "error": "Password must be at least 8 characters"}
        request = _JsonRequest(
            {
                "username": "admin",
                "password": "short",
                "setup_token": "setup-token",
            }
        )

        with patch.object(system_router.system_service, "initial_setup", return_value=failure):
            response = await system_router.setup(request, ctx)

        assert response.status_code == 400
        assert json.loads(response.body) == failure

    @pytest.mark.asyncio
    async def test_update_config_returns_server_error_when_persistence_fails(self):
        """The settings endpoint must not report HTTP success for a failed write."""
        ctx = _make_test_ctx()
        failure = {"success": False, "error": "Failed to persist configuration"}

        with patch.object(system_router.system_service, "update_config", return_value=failure):
            response = await system_router.update_config(_JsonRequest({"comic_dir": "/new/path"}), ctx)

        assert response.status_code == 500
        assert json.loads(response.body) == failure

    @pytest.mark.asyncio
    async def test_update_config_returns_bad_request_for_validation_failure(self):
        """Invalid settings payloads keep the 400 contract separate from storage errors."""
        ctx = _make_test_ctx()
        failure = {"success": False, "error": "No valid config keys provided"}

        with patch.object(system_router.system_service, "update_config", return_value=failure):
            response = await system_router.update_config(_JsonRequest({"api_key": "hacked"}), ctx)

        assert response.status_code == 400
        assert json.loads(response.body) == failure


def _make_real_config(tmp_path, monkeypatch):
    """Build a real Config with an isolated parser and no configure side effects."""
    from comicarr import config as config_module
    from comicarr import encrypted as encrypted_module

    config_path = tmp_path / "config.ini"
    config_path.write_text("")
    secure_dir = tmp_path / "secure"
    secure_dir.mkdir()

    monkeypatch.setattr(config_module, "config", configparser.ConfigParser())
    encrypted_module._fernet_instance = None

    cfg = config_module.Config(str(config_path))
    cfg.config_vals()
    cfg.SECURE_DIR = str(secure_dir)
    config_module.config.set("General", "secure_dir", str(secure_dir))
    cfg.provider_sequence = MagicMock()
    monkeypatch.setattr(comicarr, "CONFIG", cfg)
    monkeypatch.setattr(comicarr, "DATA_DIR", str(tmp_path))
    return cfg, config_path, config_module


def _symlink_or_skip(link_path, target_path):
    try:
        link_path.symlink_to(target_path)
    except (OSError, NotImplementedError) as e:
        pytest.skip("symlinks unavailable: %s" % e)


class TestConfigTransactions:
    def test_locked_value_write_processes_before_provider_sequence(self, tmp_path, monkeypatch):
        """Provider payloads are applied before sequencing without releasing the write lock."""
        cfg, _config_path, _config_module = _make_real_config(tmp_path, monkeypatch)
        events = []
        original_process = cfg.process_kwargs

        def tracked_process(values):
            events.append("process")
            original_process(values)

        def tracked_atomic_replace(_target, _mode, _write_content, binary=False):
            assert binary is False
            events.append("write")

        cfg.process_kwargs = tracked_process
        cfg.provider_sequence = MagicMock(side_effect=lambda: events.append("provider_sequence"))
        cfg._atomic_replace_file = tracked_atomic_replace

        assert cfg.writeconfig_values({"COMIC_DIR": "/ordered/library"}) is True

        assert cfg.COMIC_DIR == "/ordered/library"
        assert events == ["process", "provider_sequence", "write"]

    def test_writeconfig_values_restores_runtime_when_write_fails(self, tmp_path, monkeypatch):
        """Failed value writes must not leave process_kwargs mutations in memory."""
        cfg, _config_path, _config_module = _make_real_config(tmp_path, monkeypatch)
        original_dir = cfg.COMIC_DIR

        def fail_write(*_args, **_kwargs):
            raise OSError("simulated replace failure")

        cfg._atomic_replace_file = fail_write

        assert cfg.writeconfig_values({"COMIC_DIR": "/should-not-stick"}) is False
        assert cfg.COMIC_DIR == original_dir

    def test_incomplete_file_restore_halts_further_writes(self, tmp_path, monkeypatch):
        """After a durable write, failed file restore blocks subsequent config writes."""
        cfg, config_path, _config_module = _make_real_config(tmp_path, monkeypatch)
        original_dir = cfg.COMIC_DIR
        cfg.configure = MagicMock(side_effect=RuntimeError("configure boom"))

        real_restore_state = cfg._restore_transaction_state

        def restore_state_ok(*args, **kwargs):
            return real_restore_state(*args, **kwargs)

        def restore_file_fail(*_args, **_kwargs):
            raise OSError("simulated file restore failure")

        cfg._restore_transaction_state = restore_state_ok
        cfg._restore_config_file = restore_file_fail

        assert cfg.apply_transaction({"COMIC_DIR": "/new/library"}) is False
        assert getattr(cfg, "_config_write_halted", False) is True
        assert cfg.COMIC_DIR == original_dir
        assert cfg.apply_transaction({"COMIC_DIR": "/another/library"}) is False
        assert cfg.writeconfig() is False

    def test_transaction_encrypts_disk_secret_and_keeps_runtime_decrypted(self, tmp_path, monkeypatch):
        """A successful settings write persists ciphertext before configure runs."""
        cfg, config_path, _config_module = _make_real_config(tmp_path, monkeypatch)
        events = []
        original_write = cfg.writeconfig

        def tracked_write():
            events.append("write")
            return original_write()

        cfg.writeconfig = MagicMock(side_effect=tracked_write)
        cfg.configure = MagicMock(side_effect=lambda **_kwargs: events.append("configure"))
        secret = "transaction-test-secret"

        assert cfg.apply_transaction({"AI_API_KEY": secret}) is True

        persisted = configparser.ConfigParser()
        persisted.read(config_path)
        persisted_secret = persisted.get("AI", "ai_api_key")
        assert persisted_secret.startswith("gAAAAA")
        assert secret not in config_path.read_text()
        assert cfg.AI_API_KEY == secret
        assert cfg.ENCRYPT_PASSWORDS is True
        assert events == ["write", "configure"]
        cfg.writeconfig.assert_called_once_with()

    def test_transaction_preserves_existing_config_file_mode(self, tmp_path, monkeypatch):
        """Atomic replacement retains the permissions of an existing config file."""
        cfg, config_path, _config_module = _make_real_config(tmp_path, monkeypatch)
        os.chmod(config_path, 0o640)
        cfg.configure = MagicMock()

        assert cfg.apply_transaction({"COMIC_DIR": "/new/library"}) is True

        assert stat.S_IMODE(config_path.stat().st_mode) == 0o640

    def test_transaction_creates_new_config_file_with_private_mode(self, tmp_path, monkeypatch):
        """A first durable config write creates config.ini with mode 0600."""
        cfg, config_path, config_module = _make_real_config(tmp_path, monkeypatch)
        config_path.unlink()
        cfg.configure = MagicMock()
        replaced_modes = []
        real_replace = os.replace

        def checked_replace(source, destination):
            if config_module.Path(destination) == config_path:
                replaced_modes.append(stat.S_IMODE(os.stat(source).st_mode))
            real_replace(source, destination)

        monkeypatch.setattr(config_module.os, "replace", checked_replace)

        assert cfg.apply_transaction({"COMIC_DIR": "/new/library"}) is True

        assert replaced_modes == [0o600]
        assert stat.S_IMODE(config_path.stat().st_mode) == 0o600

    def test_normal_write_ignores_hostile_predictable_temp_symlink(self, tmp_path, monkeypatch):
        """A pre-created legacy .tmp symlink cannot redirect config output."""
        cfg, config_path, _config_module = _make_real_config(tmp_path, monkeypatch)
        victim = tmp_path / "victim.txt"
        victim.write_text("untouched")
        predictable_temp = tmp_path / "config.ini.tmp"
        _symlink_or_skip(predictable_temp, victim)
        cfg.configure = MagicMock()

        assert cfg.apply_transaction({"COMIC_DIR": "/new/library"}) is True

        assert victim.read_text() == "untouched"
        assert predictable_temp.is_symlink()
        assert config_path.is_file()

    def test_rollback_ignores_hostile_predictable_temp_symlink(self, tmp_path, monkeypatch):
        """A pre-created legacy .rollback symlink cannot redirect rollback output."""
        cfg, config_path, _config_module = _make_real_config(tmp_path, monkeypatch)
        cfg.process_kwargs({"COMIC_DIR": "/old/library"})
        assert cfg.writeconfig() is True
        victim = tmp_path / "victim.txt"
        victim.write_text("untouched")
        predictable_rollback = tmp_path / "config.ini.rollback"
        _symlink_or_skip(predictable_rollback, victim)
        cfg.configure = MagicMock(side_effect=RuntimeError("configure failed"))

        assert cfg.apply_transaction({"COMIC_DIR": "/new/library"}) is False

        assert victim.read_text() == "untouched"
        assert predictable_rollback.is_symlink()
        assert config_path.is_file()

    def test_transaction_preserves_config_symlink_identity(self, tmp_path, monkeypatch):
        """Atomic updates replace a symlink's target without replacing the link itself."""
        cfg, config_path, _config_module = _make_real_config(tmp_path, monkeypatch)
        cfg.process_kwargs({"COMIC_DIR": "/old/library"})
        assert cfg.writeconfig() is True
        target_path = tmp_path / "real-config.ini"
        config_path.replace(target_path)
        _symlink_or_skip(config_path, target_path)
        cfg.configure = MagicMock()

        assert cfg.apply_transaction({"COMIC_DIR": "/new/library"}) is True

        assert config_path.is_symlink()
        persisted = configparser.ConfigParser()
        persisted.read(target_path)
        assert persisted.get("Import", "comic_dir") == "/new/library"

    def test_unique_temp_is_cleaned_after_replace_failure(self, tmp_path, monkeypatch):
        """A failed replace removes only the exclusive temp created for that write."""
        cfg, config_path, config_module = _make_real_config(tmp_path, monkeypatch)
        replacement_sources = []
        real_replace = os.replace

        def failing_replace(source, destination):
            if config_module.Path(destination) == config_path:
                replacement_sources.append(config_module.Path(source))
                raise OSError("replace failed")
            real_replace(source, destination)

        monkeypatch.setattr(config_module.os, "replace", failing_replace)

        assert cfg.writeconfig(values={"COMIC_DIR": "/new/library"}) is False

        assert len(replacement_sources) == 1
        created_temp = replacement_sources[0]
        assert created_temp.name.startswith(".comicarr-config-")
        assert len(created_temp.name) <= 64
        assert not created_temp.exists()

    @pytest.mark.parametrize("fchmod_behavior", ["missing", "not-implemented"])
    def test_config_write_falls_back_when_fchmod_unavailable(self, tmp_path, monkeypatch, fchmod_behavior):
        """Platforms without fchmod still persist through a chmod fallback."""
        cfg, config_path, config_module = _make_real_config(tmp_path, monkeypatch)
        config_path.unlink()
        cfg.configure = MagicMock()
        if fchmod_behavior == "missing":
            monkeypatch.setattr(config_module.os, "fchmod", None)
        else:
            monkeypatch.setattr(
                config_module.os,
                "fchmod",
                MagicMock(side_effect=NotImplementedError),
            )

        assert cfg.apply_transaction({"COMIC_DIR": "/new/library"}) is True
        assert config_path.is_file()
        if os.name != "nt":
            assert stat.S_IMODE(config_path.stat().st_mode) == 0o600

    def test_transaction_restores_parser_runtime_and_file_after_write_failure(self, tmp_path, monkeypatch):
        """A failed atomic write rolls every staged config representation back."""
        cfg, config_path, config_module = _make_real_config(tmp_path, monkeypatch)
        cfg.process_kwargs({"COMIC_DIR": "/old/library"})
        original_file = config_path.read_bytes()
        writer = MagicMock(return_value=False)
        configure = MagicMock()
        cfg.writeconfig = writer
        cfg.configure = configure

        assert cfg.apply_transaction({"COMIC_DIR": "/new/library"}) is False

        assert cfg.COMIC_DIR == "/old/library"
        assert config_module.config.get("Import", "comic_dir") == "/old/library"
        assert config_path.read_bytes() == original_file
        writer.assert_called_once_with()
        configure.assert_not_called()

    def test_transaction_does_not_write_when_secret_encryption_fails(self, tmp_path, monkeypatch):
        """Plaintext secrets never reach the writer when encryption cannot complete."""
        cfg, config_path, config_module = _make_real_config(tmp_path, monkeypatch)
        writer = MagicMock(return_value=True)
        cfg.writeconfig = writer
        cfg.configure = MagicMock()
        cfg.encrypt_items = MagicMock()

        assert cfg.apply_transaction({"AI_API_KEY": "unpersisted-test-secret"}) is False

        assert cfg.AI_API_KEY is None
        assert config_module.config.get("AI", "ai_api_key") == "None"
        assert "unpersisted-test-secret" not in config_path.read_text()
        writer.assert_not_called()
        cfg.configure.assert_not_called()

    def test_unrelated_transaction_keeps_git_auth_tuple_flat(self, tmp_path, monkeypatch):
        """Repeated configure normalization keeps requests auth as a two-string tuple."""
        cfg, _config_path, _config_module = _make_real_config(tmp_path, monkeypatch)
        cfg.GIT_TOKEN = ("git-token", "x-oauth-basic")
        cfg.configure = MagicMock(side_effect=lambda **_kwargs: cfg._normalize_git_token_auth())

        assert cfg.apply_transaction({"COMIC_DIR": "/new/library"}) is True

        assert cfg.GIT_TOKEN == ("git-token", "x-oauth-basic")
        assert all(isinstance(part, str) for part in cfg.GIT_TOKEN)

    def test_transaction_restores_durable_file_when_configure_fails(self, tmp_path, monkeypatch):
        """A post-write configure failure restores the last durable configuration."""
        cfg, config_path, config_module = _make_real_config(tmp_path, monkeypatch)
        cfg.process_kwargs({"COMIC_DIR": "/old/library"})
        assert cfg.writeconfig() is True
        original_file = config_path.read_bytes()
        original_write = cfg.writeconfig
        writer = MagicMock(side_effect=original_write)
        cfg.writeconfig = writer
        cfg.configure = MagicMock(side_effect=RuntimeError("configure failed"))

        assert cfg.apply_transaction({"COMIC_DIR": "/new/library"}) is False

        assert cfg.COMIC_DIR == "/old/library"
        assert config_module.config.get("Import", "comic_dir") == "/old/library"
        assert config_path.read_bytes() == original_file
        writer.assert_called_once_with()

    def test_transaction_restores_state_when_configure_raises_system_exit(self, tmp_path, monkeypatch):
        """SystemExit from legacy configure cannot bypass transactional rollback."""
        cfg, config_path, config_module = _make_real_config(tmp_path, monkeypatch)
        cfg.process_kwargs({"COMIC_DIR": "/old/library"})
        assert cfg.writeconfig() is True
        original_file = config_path.read_bytes()
        cfg.configure = MagicMock(side_effect=SystemExit(1))

        assert cfg.apply_transaction({"COMIC_DIR": "/new/library"}) is False

        assert cfg.COMIC_DIR == "/old/library"
        assert config_module.config.get("Import", "comic_dir") == "/old/library"
        assert config_path.read_bytes() == original_file

    def test_direct_writer_waits_for_failed_transaction_rollback(self, tmp_path, monkeypatch):
        """A concurrent direct writer cannot be erased by another transaction's rollback."""
        cfg, config_path, config_module = _make_real_config(tmp_path, monkeypatch)
        cfg.process_kwargs({"COMIC_DIR": "/old/library", "DESTINATION_DIR": "/old/destination"})
        assert cfg.writeconfig() is True

        configure_entered = threading.Event()
        release_configure = threading.Event()
        direct_writer_started = threading.Event()
        direct_writer_done = threading.Event()
        results = {}

        def failing_configure(**_kwargs):
            configure_entered.set()
            assert release_configure.wait(timeout=2)
            raise RuntimeError("configure failed")

        def transactional_writer():
            results["transaction"] = cfg.apply_transaction({"COMIC_DIR": "/transaction/library"})

        def direct_writer():
            direct_writer_started.set()
            results["direct"] = cfg.writeconfig(values={"DESTINATION_DIR": "/direct/destination"})
            direct_writer_done.set()

        cfg.configure = failing_configure
        transaction_thread = threading.Thread(target=transactional_writer)
        direct_thread = threading.Thread(target=direct_writer)
        transaction_thread.start()
        assert configure_entered.wait(timeout=2)
        direct_thread.start()

        try:
            assert direct_writer_started.wait(timeout=2)
            direct_writer_was_blocked = not direct_writer_done.wait(timeout=0.1)
        finally:
            release_configure.set()
            transaction_thread.join(timeout=2)
            direct_thread.join(timeout=2)

        assert direct_writer_was_blocked
        assert not transaction_thread.is_alive()
        assert not direct_thread.is_alive()
        assert results == {"transaction": False, "direct": True}
        assert cfg.COMIC_DIR == "/old/library"
        assert cfg.DESTINATION_DIR == "/direct/destination"
        assert config_module.config.get("Import", "comic_dir") == "/old/library"
        assert config_module.config.get("General", "destination_dir") == "/direct/destination"

        persisted = configparser.ConfigParser()
        persisted.read(config_path)
        assert persisted.get("Import", "comic_dir") == "/old/library"
        assert persisted.get("General", "destination_dir") == "/direct/destination"
