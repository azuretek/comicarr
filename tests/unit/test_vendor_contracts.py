#  Copyright (C) 2025–2026 Comicarr contributors
#
#  This file is part of Comicarr.
#
#  Comicarr is free software: you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.

"""Contract tests for Comicarr-owned torrent adapter boundaries."""

from pathlib import Path
from unittest.mock import patch

import pytest

from comicarr._vendor import provenance
from comicarr.torrent import contracts
from comicarr.torrent.clients import deluge, qbittorrent, transmission, utorrent


def test_connection_result_normalizer_preserves_failure_details():
    failure = contracts.connection_failure("connection refused")

    assert failure == {"status": False, "error": "connection refused"}
    assert contracts.normalize_connection_result(False, error="connection refused") == failure


def test_monitor_error_always_has_established_status_shape():
    assert contracts.monitor_error("vendor unavailable") == {
        "snatch_status": "MONITOR ERROR",
        "error": "vendor unavailable",
    }


def test_deluge_repeated_connect_returns_existing_client():
    adapter = deluge.TorrentClient()
    existing = object()
    adapter.client = existing
    adapter.conn = existing

    assert adapter.connect("localhost:58846", "user", "password") is existing


def test_deluge_malformed_host_is_connection_failure():
    adapter = deluge.TorrentClient()

    result = adapter.connect("localhost", "user", "password")

    assert result == {"status": False, "error": "invalid host; expected host:port"}


def test_qbittorrent_repeated_connect_returns_existing_client():
    adapter = qbittorrent.TorrentClient()
    existing = object()
    adapter.client = existing
    adapter.conn = existing

    assert adapter.connect("http://localhost:8080", "user", "password") is existing


def test_qbittorrent_connect_exception_is_normalized():
    adapter = qbittorrent.TorrentClient()

    with patch.object(qbittorrent, "Client", side_effect=RuntimeError("boom")):
        result = adapter.connect("http://localhost:8080", "user", "password")

    assert result["status"] is False
    assert "boom" in str(result["error"])


def test_transmission_connect_exception_is_normalized():
    adapter = transmission.TorrentClient()

    with patch.object(transmission, "Client", side_effect=RuntimeError("boom")):
        result = adapter.connect("localhost:9091", "user", "password")

    assert result["status"] is False
    assert "boom" in str(result["error"])


def test_transmission_repeated_connect_returns_existing_connection():
    adapter = transmission.TorrentClient()
    existing = object()
    adapter.conn = existing

    assert adapter.connect("localhost:9091", "user", "password") is existing


def test_utorrent_connect_exception_is_normalized():
    adapter = utorrent.TorrentClient()

    with patch.object(utorrent, "UTorrentClient", side_effect=RuntimeError("boom")):
        result = adapter.connect("http://localhost:8080", "user", "password")

    assert result["status"] is False
    assert "boom" in str(result["error"])


def test_vendor_manifest_covers_packaged_runtime_vendors():
    vendor_root = Path(__file__).parents[2] / "comicarr" / "_vendor"
    packages = {path.name for path in vendor_root.iterdir() if path.is_dir() and (path / "__init__.py").exists()}

    assert packages <= set(provenance.VENDOR_PROVENANCE)
    assert all(provenance.VENDOR_PROVENANCE[name]["owner"] == "Comicarr" for name in packages)


@pytest.mark.parametrize(
    "adapter_module",
    [deluge, qbittorrent, transmission],
)
def test_adapters_do_not_import_top_level_vendor_names(adapter_module):
    source = Path(adapter_module.__file__).read_text(encoding="utf-8")

    assert "comicarr._vendor" in source
    assert "from deluge_client" not in source
    assert "from qbittorrent" not in source
    assert "from transmissionrpc" not in source
