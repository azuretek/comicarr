---
"comicarr": patch
---

Wanted filtering now searches the full queue, not only the currently loaded page. Typing a filter term sends it to `/api/wanted` so match count, pagination total, and Next/Previous all describe the same filtered result set — matches that used to sit on page 2 are no longer invisible from page 1.
