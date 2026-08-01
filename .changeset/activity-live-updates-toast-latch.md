---
"comicarr": patch
---

Open Activity surfaces now refresh the moment work happens instead of waiting out the 30s poll, and they catch up immediately after a dropped connection. Bursty work — a search run grabbing dozens of issues — costs one refresh, not one per issue.

Toasts are quieter and more useful: Comicarr interrupts you once when something starts needing attention, then stays silent until the needs-attention count clears. Routine progress no longer toasts at all. The noisy "Search Complete", "Task Complete", and duplicate "Series Added" pop-ups are gone; the Activity timeline carries that history instead. A server restart now says so, and the status bar reports `unreachable` when the connection has been down long enough to matter rather than only after the next health check.
