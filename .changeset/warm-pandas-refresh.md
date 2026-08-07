---
"comicarr": patch
---

Fixed series refresh failing outright whenever it had issue or location changes to write. Refreshing a series looked up its database table under the wrong name, so the moment a refresh found something to update — a new issue, a changed status, a relocated series folder — the write raised `Unknown table for upsert` and the whole run was recorded as failed. Refreshes that happened to find nothing to change appeared to succeed, which is why this could go unnoticed while every real update was being dropped. The same defect affected annuals, the bulk series-location update after a config change, and the dynamic-name maintenance pass. All of them now write correctly, so a refresh actually persists what it finds.
