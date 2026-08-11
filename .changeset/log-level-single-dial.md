---
"comicarr": patch
---

Changing the logging level now does what you asked for. Raising verbosity no longer silences console output — under Docker it previously did exactly that, so there was no way to get more detail out of a container. Lowering it now takes effect immediately instead of leaving the previous, noisier level in place. Quiet mode means warnings and errors only rather than near-total silence, so a failure still reaches you with the dial turned down.
