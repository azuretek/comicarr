---
"comicarr": patch
---

Keep clients, database connections, and runtime context open for terminal process exit when a scheduler job or worker remains alive after its bounded shutdown drain.
