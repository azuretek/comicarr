---
"comicarr": patch
---

Hand-edited legacy `torznab_*` fields under `[Torznab]` in config.ini no longer sit silently inert. A complete legacy entry (name, host, API key, category) is folded into the real multi-provider `extra_torznabs` list on startup and the stale keys are removed; an incomplete one is called out in the log with a pointer to the Settings UI instead of being ignored. (#631)
