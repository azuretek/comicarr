# The log level contract

Comicarr has exactly one verbosity control: the numeric level `comicarr.LOG_LEVEL`.
It resolves to a single stdlib threshold, and that same threshold is applied to
the logger and to every sink it feeds. There is no second dial.

## The dial

| Level | Threshold | Console | `comicarr.log` | Web UI log list |
| --- | --- | --- | --- | --- |
| `0` — quiet | `WARNING` | warnings and errors | warnings and errors | warnings and errors |
| `1` — normal (default) | `INFO` | info and above | info and above | info and above |
| `2` — verbose | `DEBUG` | everything | everything | everything |

Levels below `0` clamp to `WARNING`; above `2` clamp to `DEBUG`.

`logger.threshold_for_level()` is the only place this mapping lives, and
`logger.current_log_level()` is the only supported way to ask what the dial is
currently set to. Nothing else may branch on verbosity.

## Where the level comes from

The dial says what a level *means*; this says where the number is *read from*.
Three sources, highest priority first:

| Priority | Source | Set by |
| --- | --- | --- |
| 1 | a startup argument — `--log-level N`, or the `--verbose` / `--quiet` aliases | the command line, a systemd unit, a container entrypoint |
| 2 | the `COMICARR_LOG_LEVEL` environment variable | a compose file, the shell |
| 3 | `LOG_LEVEL` in `config.ini` | the Settings UI |

If none of them supplies a value, the level is `1`.

**A source counts only when it explicitly supplies a value.** That qualifier is
the whole rule, and it is what #610 got wrong: the Docker entrypoint passed
`--quiet` on every start, so the top of the chain was permanently occupied and
nothing an operator set below it could ever be heard. An argument that was not
passed must leave the layer beneath it alone. In particular, level `0` is a
value, not an absence — a falsy check here reintroduces the bug.

Resolution happens once, when config is read at startup, in
`comicarr/app/config/log_level.py`. Every source is parsed even when a
higher-priority one has already won, so an operator who typoed
`COMICARR_LOG_LEVEL` is told about it, and the winning source announces what it
overrode.

Values outside `0`–`2` are clamped rather than rejected: a compose file asking
for `3` wants maximum verbosity, and refusing to boot over it helps nobody. A
non-numeric value is ignored with a notice, and the next source down is used.

`COMICARR_LOG_LEVEL` is a deliberate one-off for this one key. Comicarr does not
read the environment for any other setting, and a general `COMICARR_<KEY>`
mechanism is a separate question — it raises precedence, secrets-in-env, and
UI-honesty problems that have nothing to do with logging.

### Saving the level from Settings applies it now

The Settings page is not part of the startup chain: it writes `LOG_LEVEL` to
`config.ini` *and* reconfigures the running logger, so the change takes effect
without a restart. The whole point of turning verbosity up is to catch a
problem while it is happening, and a dial that waits for a restart destroys the
state the operator was trying to capture.

`update_config` (`comicarr/app/system/service.py`) persists first and calls
`logger.configure_log_level()` after — a level that survives the restart but is
not yet live is a much smaller failure than a live level the next start
forgets. If the reconfigure fails (a log directory that has become unwritable
is the realistic case), the save still reports success and the failure is
logged; the level applies at the next start.

The value is read by `parse_level`, exactly as the three startup sources are,
so a level typed into Settings clamps to range the same way. It differs on one
point: a non-numeric value is *refused* with an error rather than ignored. A
startup source has a layer beneath it to fall through to, and an HTTP request
has somewhere to put the complaint — persisting `"verbose"` would leave the
operator's setting silently discarded at the next start.

On the next start the chain runs again, so a startup argument or
`COMICARR_LOG_LEVEL` will override what Settings saved. That is the documented
precedence, and it is why the winning source announces what it overrode.

### `--quiet` and `--verbose`

`--quiet` is a deprecated alias for `--log-level 0` and prints a notice saying
so. It stays because it is in existing compose files and systemd units; deleting
it would break them for a cosmetic gain. `--verbose` maps to level `2`. When
more than one is passed, `--log-level` wins, then `--verbose`, then `--quiet`.

### The two helpers disagree about `None`, on purpose

`comicarr.LOG_LEVEL` is `None` until configuration is read, and the two helpers
resolve that differently. This is deliberate, not an oversight:

- `threshold_for_level(None)` → `INFO`. It answers *"how should the sinks be
  configured?"*, and an unconfigured process should log normally rather than
  start half-muted. In practice both callers pass a resolved integer, so this
  is a defensive default rather than a live path.
- `current_log_level()` → `0`. It answers *"how loud is the operator asking us
  to be right now?"*, and before the config says otherwise the conservative
  answer is the quiet one.

Picking one shared value would break a caller either way. Making
`current_log_level()` return `1` would stop the first-run setup token from being
echoed to stdout before config load — and losing that token means the operator
cannot finish setup at all. Making `threshold_for_level(None)` return `WARNING`
would silently downgrade default logging. So they stay distinct, and callers
choose by what they are actually asking.

## Two rules that fall out of it

**Level 0 is "warnings and errors", not silence.** An operator who turns the
dial down is asking for less noise, not for failures to be hidden. This is why
the setup-token announcement in `app/system/service.py` echoes to stdout at
level 0: the token is logged at `INFO`, so at level 0 it would otherwise never
reach an operator who has no other way to finish first-run setup.

**Console attachment is a deployment concern, not a verbosity one.** Whether a
`StreamHandler` exists at all is the explicit `console=` argument to
`initLogger()`, and it is orthogonal to the level. Both current callers pass
`True`; the parameter exists so that a future daemon or embedded mode can
detach stdout without inventing a second verbosity flag.

Together these are what let `--quiet` be a plain alias for level `0` rather
than a flag with its own hidden second effect.

## What this replaced

`comicarr.QUIET` was that hidden second effect. `--quiet` set it, nothing ever
cleared it, and five sites read it independently to decide whether output
should appear. It is retired and guarded by `scripts/check_retired_globals.py`.

Three defects came out of it, all fixed alongside the retirement:

- `configure_log_level()` computed `console=QUIET if level == 0 else not QUIET`.
  Under Docker — which always passed `--quiet` — that inverted expression meant
  raising verbosity **removed** the console sink. This is the defect reported in
  #610: the operator could not get more output by asking for more output.
- `initLogger()` set a level only for `loglevel == 1` and `loglevel >= 2`. At
  level 0 it left the logger untouched, so lowering verbosity at runtime kept
  the previous, more verbose threshold, and a fresh level-0 start inherited
  root's `WARNING` by accident rather than by design.
- Failing to create the log directory dropped `LOG_DIR` only when `QUIET` was
  false, so a quiet process kept an uncreatable path and lost the recovery.

## Not covered here — and "not covered" includes Docker

The `RotatingLogger` path (`logger.py`, taken when `LOG_LANG` does not start
with `en`) does **not** implement this contract. Read it as the *non-English*
path and you will conclude it is a rare edge case. It is not:

**Every Docker install takes it.** `python:3.12-slim` sets `LANG=C.UTF-8`, so
`locale.getdefaultlocale()` returns `('C', 'UTF-8')` and `LOG_LANG` is `"C"`.
Verified inside an image built from this repo — the giveaway in `docker logs` is
the message format, `INFO :: MainThread : maintenance.py:backup_files:539 :`
rather than the English path's `INFO :: comicarr.backup_files.539 : MainThread`.

On that path the dial is enforced in the module-level `debug()` / `info()`
wrappers rather than by handler levels, so the log *file* does follow it. The
console does not: `initLogger` creates the `StreamHandler` inside `if loglevel:`,
so **level 0 attaches no console sink at all** and `docker logs` goes silent
rather than showing warnings and errors. That is the same shape as the #610
defect — a level that removes a sink instead of raising its threshold — and it
is why the contract's "level 0 is not silence" rule is currently aspirational
for containers.

One consequence worth knowing before designing a fix: a single `ENV
LANG=en_US.UTF-8` in the `Dockerfile` would move every container onto the
contract-compliant path without touching `logger.py`. Whether that, adopting the
contract in `RotatingLogger`, or retiring the path is right is the decision on
[Decide the fate of the non-English RotatingLogger path](https://github.com/frankieramirez/comicarr/issues/619),
under [Wayfinder: One log level dial, everywhere](https://github.com/frankieramirez/comicarr/issues/611).
