---
"comicarr": patch
---

Comicarr images are now published to Docker Hub as `comicarr/comicarr`, mirroring the existing GHCR images tag for tag from the same build. `docker pull comicarr/comicarr:latest` works, matching what the website has been advertising. Nothing changes for existing installs — `ghcr.io/frankieramirez/comicarr` remains the canonical reference and is still what the update instructions point at, since GHCR does not rate-limit anonymous pulls.
