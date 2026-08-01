---
"comicarr": minor
---

Comicarr now judges update availability against the Changesets release line (GitHub `releases/latest`) instead of git commits. `GET /api/system/version` exposes `update_state` (`behind` / `current` / `unknown`), a v-stripped `latest_version`, and the local `release_version`. Automatic release checks are **on by default** (including existing installs after config migration to v16) and run on startup for every install type on a 6-hour cadence. Comicarr contacts GitHub every 6 hours for these checks; set `check_github = False` in `config.ini` to opt out. The dead `check_update` toast path and `AUTO_UPDATE` / `CHECK_GITHUB_ON_STARTUP` settings are retired.
