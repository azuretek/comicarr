---
"comicarr": minor
---

The dashboard's **Recent activity** panel now reads the same narrative stream as the Activity Center, so a failed grab or blocked download appears in the timeline instead of vanishing because it never reached the snatched table. That is the failure mode that let a broken downloader look like a quiet week: the old panel could only list things that had already been snatched.

Each row uses the same sentence voice and deep-links as the Activity Center — failures read "Couldn't grab…", successes read "Grabbed…", and the subject links through to the issue or series. When nothing has happened, the empty state says **No activity in the last 30 days** and links into the full activity view, not the download-history table.
