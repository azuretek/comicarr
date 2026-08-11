---
"comicarr": patch
---

Warnings and errors now reach your logs on Docker. Comicarr chose between two different logging implementations based on your system locale, and the one containers ended up on was missing pieces: certain warnings — "No COMIC_DIR configured", "Cannot find import directory", and others like them — raised an internal error instead of being written down, and unexpected failures were dropped entirely while the server tried to record them. Startup even announced it: *"errors WILL NOT be captured in the logs"*. There is one logging implementation now, the same for every locale, so those messages appear in `comicarr.log`, in `docker logs`, and in the log list in the Web UI like everything else.

Two things to expect after upgrading. Log lines from containers change shape slightly — `INFO :: comicarr.backup_files.539 : MainThread` in place of `INFO :: MainThread : maintenance.py:backup_files:539 :` — so an existing log file will show both styles either side of the upgrade. And with the dial turned all the way down, `docker logs` now shows warnings and errors rather than nothing at all, which is what level 0 was always meant to mean.
