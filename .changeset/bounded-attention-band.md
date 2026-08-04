---
"comicarr": minor
---

The needs-attention band no longer buries the Activity timeline. Instead of one red row per failure — several hundred of them on a busy install, pushing the feed off the bottom of the page — the band now shows at most five cards in a single fixed-height row, and the timeline sits directly beneath it no matter how much has gone wrong.

Failures are grouped by series and cause, so a restart that stranded 47 issues of one title reads as one card marked `×47` rather than 47 identical lines. Each card names the series, says what went wrong in plain language instead of `downloaded_invalid_artifact_command:PostProcessCommandError`, and is colour-coded by what it wants from you: red when Comicarr couldn't finish, amber when it's waiting on your decision. Newest trouble ranks first.

A new **Needs attention** page at `/activity/attention` is where you actually work through them. It lists every group, filters by stage and age, searches by series or reason, and lets you select several at once. The `⚠ N need attention` count in the status bar now counts distinct problems rather than rows, and clicking it lands here. Activity keeps its three tabs — Timeline, Direct Downloads, Download History — unchanged.

Group and bulk actions fan out over every issue behind a card in one click. Failures are per-issue: if one of sixteen can't be retried, the other fifteen still clear and you get told which one didn't, rather than losing the whole batch. Comicarr processes 25 issues per action and says how many it left for the next click.

**Ignore is now Stop wanting**, everywhere. It always meant "mark this ignored in the library and stop searching for it" — not "dismiss this alert" — and the old name invited the wrong reading. Stopping two or more issues at once now asks you to confirm, naming the series, the count, and what happens.
