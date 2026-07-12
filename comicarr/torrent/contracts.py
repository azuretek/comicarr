#  Copyright (C) 2025–2026 Comicarr contributors
#
#  This file is part of Comicarr.
#
#  Comicarr is free software: you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.

"""Comicarr-owned contracts shared by torrent client adapters."""

from collections.abc import Mapping
from typing import Any, Protocol, TypedDict


class ConnectionFailure(TypedDict):
    """Stable failure shape returned when a client cannot connect."""

    status: bool
    error: str


class MonitorError(TypedDict):
    """Stable status shape consumed by recovery and monitor workers."""

    snatch_status: str
    error: str


class TorrentAdapter(Protocol):
    """Minimum adapter surface used by the RSS and recovery workers."""

    def connect(self, host: str, username: str, password: str, *args: Any, **kwargs: Any) -> Any:
        """Connect once and return the client or a ``ConnectionFailure``."""

    def find_torrent(self, torrent_hash: str) -> Any:
        """Look up a torrent by its client-specific identifier."""

    def get_torrent(self, torrent: Any) -> Mapping[str, Any] | bool:
        """Return a normalized torrent record or ``False`` when absent."""

    def start_torrent(self, torrent: Any) -> bool:
        """Start a torrent and report whether the request succeeded."""

    def stop_torrent(self, torrent: Any) -> bool:
        """Pause a torrent and report whether the request succeeded."""

    def delete_torrent(self, torrent: Any) -> Any:
        """Delete a torrent and return deleted paths or a falsey result."""


def connection_failure(error: object) -> ConnectionFailure:
    """Build the adapter-level connection failure shape."""

    return {"status": False, "error": str(error)}


def normalize_connection_result(result: Any, *, error: object = "client did not connect") -> Any:
    """Preserve successful vendor objects while normalizing falsey failures."""

    if result is None or result is False:
        return connection_failure(error)
    if isinstance(result, Mapping) and result.get("status") is False:
        return connection_failure(result.get("error", error))
    return result


def monitor_error(error: object) -> MonitorError:
    """Build the monitor error shape used by ``torrentinfo`` callers."""

    return {"snatch_status": "MONITOR ERROR", "error": str(error)}
