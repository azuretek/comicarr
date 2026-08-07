---
"comicarr": patch
---

Fixed searches aborting and providers going dark for an hour whenever an indexer returned any error at all. A rate-limit response — Prowlarr's plain HTTP 429, the most common thing an indexer says when you search too often — was treated identically to the indexer being unreachable: Comicarr blocklisted the provider and abandoned the search. The check meant to distinguish the two cases had been written so that it always fired, so in practice every transient hiccup cost you the whole search cycle, and the next one 6 hours later. Comicarr now inspects the actual failure: if the provider answered at all, it is left enabled and only that one search is skipped, and only a genuine connection failure (refused, timed out, host or network unreachable) blocklists it. The same fix applies to the GetComics DDL provider. These failures also no longer dump a 130-entry table of system error codes into your logs on every occurrence.
