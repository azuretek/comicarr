---
"comicarr": minor
---

Update checks now compare the Changesets release version against GitHub `releases/latest` (semver `behind` / `current` / `unknown`) instead of counting commits. `GET /api/system/version` exposes `update_state`, `update_reason`, `release_version`, and a v-stripped `latest_version`; `commits_behind` is gone. Automatic release checks default **on** for new and existing installs (config version 16 rewrites a still-`False` `CHECK_GITHUB` to `True`). Comicarr contacts GitHub every 6 hours when checking is enabled — set `check_github = False` under `[Git]` in `config.ini` to opt out. The dead update toast path and `AUTO_UPDATE` self-apply are retired.
