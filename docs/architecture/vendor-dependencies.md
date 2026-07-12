# Vendor dependencies and client contracts

This document is the source of truth for code that is shipped inside
`comicarr._vendor`. Vendor code is intentionally namespaced; torrent and
downloader integrations are imported through Comicarr-owned adapters, while
the ComicTagger entry point imports its internal package explicitly. The
application no longer relies on a process-wide `sys.path` mutation or an
undeclared top-level package.

Inventory and review date: 2026-07-11. The source tree at the Plan 004 base
(`0f31ad35`) was used for the initial provenance review. The package names
below are checked by `tests/unit/test_vendor_contracts.py` and the ownership
metadata in `comicarr/_vendor/provenance.py`.

## Runtime ownership matrix

| Runtime capability | Comicarr importer(s) | Packaged owner | Source/version recorded in tree | License/provenance status | Decision |
| --- | --- | --- | --- | --- | --- |
| Deluge RPC | `comicarr.torrent.clients.deluge` | `comicarr._vendor.deluge_client` | Bundled RPC client; source headers plus `LICENSE` | MIT notices retained in vendor tree | Retain as an internal vendor behind the adapter until a Deluge 2.x compatibility fixture exists |
| qBittorrent Web API | `comicarr.torrent.clients.qbittorrent` | `comicarr._vendor.qbittorrent` | Bundled Web API client; source revision not separately recorded | `LICENSE` retained; confirm upstream revision before replacement | Retain behind the adapter; evaluate `qbittorrent-api` only after matching category/save-path/auth behavior |
| Transmission RPC | `comicarr.torrent.clients.transmission` | `comicarr._vendor.transmissionrpc` | Bundled client `0.11` | MIT notice retained in source | Retain behind the adapter; `transmission-rpc` is a candidate but requires a protocol/field compatibility fixture |
| rTorrent XML-RPC/SCGI | `comicarr.torrent.clients.rtorrent` | `comicarr._vendor.rtorrent` | Bundled rTorrent client `0.2.9` | MIT notices retained in source | Retain behind the adapter; no flag-day replacement is justified |
| uTorrent Web API | `comicarr.torrent.clients.utorrent`, legacy `comicarr.utorrent` | `comicarr._vendor.utorrent` | Bundled uTorrent 3.x client | Upstream license status is not explicit in the copied tree; legal review required | Retain for configured users; do not add a new dependency until provenance is resolved |
| Mega downloads | `comicarr.downloaders.mega` | `comicarr._vendor.mega` | Bundled `mega.py` implementation | Upstream license status requires legal review before redistribution | Retain behavior behind the downloader boundary; no replacement selected |
| ComicTagger metadata | `comicarr/config.py`, `comictagger.py` | `comicarr._vendor.comictaggerlib` | Bundled ComicTagger `1.3.5` (`ctversion.py`) | Upstream notices are preserved; archive/tagging fixture required before relocation or upgrade | Retain as a separately reviewed subphase; do not change tagging behavior in this migration |
| Torrent bencode/hash support | `comicarr.app.common.utilities`, torrent adapters, recovery helpers | `comicarr._vendor.bencode` and `comicarr._vendor.rtorrent.lib.bencode` | Bundled helper implementations | Source notices retained; no external dependency selected | Retain as internal support code and keep hashing behind Comicarr helpers |

The only runtime vendor imports found in the base inventory were Deluge,
qBittorrent, Transmission, rTorrent, uTorrent, Mega, ComicTagger, and bencode.
`certgen.py`, `get_image_size.py`, and the nested rTorrent XML-RPC helpers are
packaged support modules rather than public integration entry points; they are
included in the same ownership boundary.

## Replacement review

The following primary project metadata was checked on 2026-07-11:

- [transmission-rpc on PyPI](https://pypi.org/project/transmission-rpc/) is
  maintained and MIT-licensed, but its documented protocol support and object
  fields must be compared with Comicarr's `get_torrent()` shape before any
  swap.
- [Deluge on PyPI](https://pypi.org/project/deluge/) is GPLv3+ and current
  Deluge releases changed the Python/RPC surface. A direct drop-in would need
  a daemon-version and error-translation fixture.
- [qbittorrent-api on PyPI](https://pypi.org/project/qbittorrent-api/) is a
  maintained qBittorrent Web API candidate with current Python support, but
  its method names and typed objects differ from the bundled client's
  `download_from_*`, category, and save-path calls.
- [mega.py on PyPI](https://pypi.org/project/mega.py/) has no recent stable
  release and carries a non-permissive license declaration; it is not adopted
  without an explicit redistribution decision.
- [ComicTagger](https://github.com/comictagger/comictagger) remains a
  behavior-sensitive archive/tagging tool. Any upgrade must compare generated
  CBL/ComicRack metadata and CBR-to-CBZ output fixtures.
- [Transmission's RPC specification](https://github.com/transmission/transmission/blob/main/docs/rpc-spec.md)
  documents deprecated legacy RPC fields, so protocol compatibility must be
  tested rather than inferred from a package name.

## Adapter contract

`comicarr.torrent.contracts` owns the narrow boundary used by search, RSS, and
recovery code:

- `connect()` returns the vendor client on success or
  `{"status": False, "error": "..."}` on failure. Repeated calls return the
  existing connection.
- `find_torrent()` and `get_torrent()` may use vendor-native identifiers, but
  failures are falsey and normalized by the adapter.
- start, pause, and delete methods return a boolean or deleted-path list;
  vendor exceptions do not leak through routine connection failures.
- monitor-facing code keeps the established dictionary shape and uses
  `snatch_status="MONITOR ERROR"` for connection or vendor failures.

The adapters deliberately do not expose vendor modules at the application
root. New integrations must add an ownership row here, update the machine-
readable provenance map, and add adapter-level fakes before changing client
selection or configuration behavior.
