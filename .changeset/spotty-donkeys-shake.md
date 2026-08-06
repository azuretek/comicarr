---
"comicarr": patch
---

Fixed the `docker pull` command in the update-available popover, which pointed at an image tag that does not exist. Comicarr publishes bare-semver tags (`0.26.0`), but the popover copied a `v`-prefixed reference (`ghcr.io/frankieramirez/comicarr:v0.26.0`) that fails with a manifest-not-found error. The surrounding advice was also incomplete: pulling an image never moves a running container onto it, but the popover implied a plain pull was enough. Both paths are now spelled out — set the pinned tag in your compose file and `up -d`, or stop and remove the container and re-run it. The README says the same.
