---
"comicarr": patch
---

Docker containers now log normally. The image used to start Comicarr with `--quiet` hardcoded, so `docker logs` showed almost nothing and no setting could raise it — the level you chose in Settings was overruled on every start. That argument is gone: containers now run at the normal level, `docker logs` shows what the server is doing, and the level is yours to set. Change it in Settings, or set `COMICARR_LOG_LEVEL` to `0`, `1`, or `2` in your compose file when you want it fixed regardless of Settings. The container banner says which of the two is in effect at startup.

Expect more output than before after upgrading — that is the fix, not a side effect. Turn it down in Settings if you want less.
