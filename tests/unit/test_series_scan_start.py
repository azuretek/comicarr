#  Copyright (C) 2025–2026 Comicarr contributors
#
#  This file is part of Comicarr.
#
#  Comicarr is free software: you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

import comicarr
from comicarr.app.series import service


@pytest.mark.parametrize(
    ("scan", "config_key", "path", "error"),
    [
        (service.comic_library_scan, "COMIC_DIR", "/missing/comics", "Comic directory not found"),
        (service.manga_library_scan, "MANGA_DIR", "/missing/manga", "Manga directory not found"),
    ],
)
def test_library_scan_rejects_missing_mount(monkeypatch, scan, config_key, path, error):
    monkeypatch.setattr(comicarr, "CONFIG", SimpleNamespace(**{config_key: path}))
    monkeypatch.setattr(service.os.path, "isdir", MagicMock(return_value=False))
    thread = MagicMock()
    monkeypatch.setattr(service.threading, "Thread", thread)

    result = scan(None)

    assert result["success"] is False
    assert error in result["error"]
    thread.assert_not_called()
