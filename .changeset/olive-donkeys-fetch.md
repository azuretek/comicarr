---
"comicarr": patch
---

Fixed a failed torrent download landing in manual review — and permanently blocking that issue from that provider — when the .torrent file simply could not be fetched. If the tracker was unreachable, timed out, or returned something unusable, Comicarr crashed inside the send step instead of reporting a clean failure. Because a crash there means "we do not know whether the download client got this", the attempt was filed for manual review, which is terminal: every later attempt on the same issue and provider was then refused before it even reached the client, so the 6-hourly search retried into the same wall forever while telling you nothing useful. A fetch that never reaches the download client is now reported as an ordinary failure and goes to Failed Download Handling, so the release can be retried normally. This affects all five torrent clients (rTorrent, Deluge, qBittorrent, Transmission, uTorrent).
