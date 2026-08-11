---
"comicarr": patch
---

Debug logging now includes useful folder-scan diagnostics without a second hidden switch. Comicarr removes the legacy `folder_scan_log_verbose` setting during the configuration upgrade; set the single Log level to `2 · Debug` when diagnosing scan matching. Candidate-heavy scans now summarize their work per input file instead of flooding the log with one line for every comparison.
