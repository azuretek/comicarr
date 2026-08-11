---
"comicarr": patch
---

The log level can now be set by name as well as by number. `warning`, `info`, and `debug` work anywhere the number did — `--log-level debug` on the command line, `COMICARR_LOG_LEVEL=debug` in your compose file, or `LOG_LEVEL = debug` in `config.ini`. Numbers are unchanged, so nothing you already have needs editing, and capitalisation does not matter.

The names describe what each level actually does: level `0` is `warning` because it emits warnings and errors. It was previously described as "quiet", which suggested silence and was never true — turning the dial down has always kept failures visible.

Startup messages now name the level both ways, so it is obvious which setting produced it: `Log level 2 (debug) from startup argument overrides 1 (info) from the config file`.

`--verbose` and `-v` are now deprecated aliases for `--log-level debug`, joining `--quiet` and `-q` (aliases for `--log-level warning`). All four keep working and will continue to — they print a note pointing at `--log-level`, which is the one flag that sets the level directly.
