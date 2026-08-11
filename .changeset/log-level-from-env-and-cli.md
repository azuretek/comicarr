---
"comicarr": patch
---

You can now set the logging verbosity without editing the config file. `--log-level 0|1|2` on the command line and the `COMICARR_LOG_LEVEL` environment variable both set it, and each is honoured only when you actually supply it — a startup argument wins over the environment variable, which wins over the level saved in Settings. An out-of-range number is clamped instead of refusing to start, an unreadable one is reported and skipped, and whichever source wins says on startup what it overrode. `--quiet` still works as before but now prints a deprecation notice pointing at `--log-level 0`.
