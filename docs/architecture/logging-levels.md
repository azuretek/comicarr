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

`None` — the value before configuration is read — resolves to level `1`.
Levels below `0` clamp to `WARNING`; above `2` clamp to `DEBUG`.

`logger.threshold_for_level()` is the only place this mapping lives, and
`logger.current_log_level()` is the only supported way to ask what the dial is
currently set to. Nothing else may branch on verbosity.

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

## Not covered here

The non-English `RotatingLogger` path (`logger.py`, taken when `LOG_LANG` does
not start with `en`) does **not** implement this contract: its file handler is
pinned at `DEBUG` and its `initLogger` takes no `console` argument at all.
Whether it adopts the contract or is retired is tracked on
[Wayfinder: One log level dial, everywhere](https://github.com/frankieramirez/comicarr/issues/611).
