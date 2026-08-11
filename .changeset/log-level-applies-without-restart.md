---
"comicarr": patch
---

The logging level you save in Settings now takes effect immediately, with no restart. Previously the new level was written to the config file and then ignored until the server came back up — which is exactly the wrong moment, since you usually turn verbosity up to catch a problem that is happening right now, and restarting throws away the state you were trying to capture. Turn the dial up, reproduce the problem, read the logs. Out-of-range numbers are clamped to `0`–`2` as they are everywhere else, and a value that is not a number is refused rather than saved and silently dropped at the next start.
