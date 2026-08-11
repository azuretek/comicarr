---
"comicarr": minor
---

Read your logs without leaving Comicarr. Settings has a new **Logs** section: the tail of `comicarr.log` in a console you can filter by severity and copy straight into a bug report, with the log level dial sitting right above it. Raise the level, reproduce the problem, and read what happened — without a shell, a `docker exec`, or a restart.

The dial is honest about who is in charge. If a `--log-level` flag or `COMICARR_LOG_LEVEL` is setting the level, the page says so, names the level actually running and the one the next restart will bring back, and explains that the value you save here applies immediately but will not survive that restart until the pin is removed. When nothing overrides it, the page stays quiet and the dial simply is what runs.

The header shows where the log file lives and how much history is kept (`10 MB × 5 files`) so you can see the ceiling before turning verbosity up. You can pull the last 200, 1,000, or 5,000 lines. Provider secrets are still redacted before any line leaves the server, and only the current log file is read — rotated files stay where they are.
