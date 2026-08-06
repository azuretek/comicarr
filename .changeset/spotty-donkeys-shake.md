---
"comicarr": patch
---

Fixed the `docker pull` command in the update-available popover, which pointed at an image tag that does not exist. Comicarr publishes bare-semver tags (`0.26.0`), but the popover copied a `v`-prefixed reference (`ghcr.io/frankieramirez/comicarr:v0.26.0`) that fails with a manifest-not-found error. The Compose note was also misleading: it implied a plain pull pins your install to a release, when a pull alone leaves a running container on `:latest`. It now tells you to set the pinned tag in your compose file.
