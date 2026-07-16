"""Directory creation logging regressions."""

from unittest.mock import MagicMock, patch


def test_missing_directory_requested_for_creation_is_not_warned(tmp_path):
    from comicarr import filechecker

    destination = tmp_path / "new-series"
    config = MagicMock()
    config.ENFORCE_PERMS = False
    config.CHMOD_DIR = "0777"

    with patch("comicarr.CONFIG", config), patch("comicarr.filechecker.logger") as mock_logger:
        result = filechecker.validateAndCreateDirectory(str(destination), create=True)

    assert result is True
    assert destination.is_dir()
    warning_text = " ".join(str(part) for call in mock_logger.warn.call_args_list for part in call.args)
    assert "Could not find comic directory" not in warning_text


def test_directory_creation_failure_still_warns(tmp_path):
    from comicarr import filechecker

    destination = tmp_path / "uncreatable"
    config = MagicMock()
    config.ENFORCE_PERMS = False
    config.CHMOD_DIR = "0777"

    with (
        patch("comicarr.CONFIG", config),
        patch("comicarr.filechecker.logger") as mock_logger,
        patch("comicarr.filechecker.os.makedirs", side_effect=OSError("permission denied")),
    ):
        result = filechecker.validateAndCreateDirectory(str(destination), create=True)

    assert result is False
    warning_text = " ".join(str(part) for call in mock_logger.warn.call_args_list for part in call.args)
    assert "Could not create directory" in warning_text
