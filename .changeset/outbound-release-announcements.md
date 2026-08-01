---
"comicarr": minor
---

When release announcements are enabled (`announce_releases = True` under `[Git]` in `config.ini`; default off), Comicarr sends **one** outbound message through every enabled notifier after a check finds the install behind — body is `{current} → {latest}` plus the GitHub release URL. The same remote version is not re-announced every check interval. Snatch/grab notifier flags are not reused.
