---
"comicarr": patch
---

Failed downloads now reach failed-handling instead of parking in Needs Attention. A download NZBGet reported as failed sits in `InterDir`, outside the configured post-processing roots, so the command was rejected on its path before anything looked at the failed flag. The grab was never marked failed, the failed-download checker never tripped, and the same broken release was re-grabbed on every later search while the issue stayed stuck in Needs Attention with no way to clear it. Failed downloads are still path-sanitised, and successful ones are still confined to the configured roots.

A previously failed release no longer rejects every alternative for the same issue. Every candidate the provider returned was checked against the *first* candidate's release id, so one failed release discarded the whole result set and the issue stayed Wanted with nothing to show for the search. Each candidate is now judged on its own, and the release that is actually snatched is the one recorded against the issue — so post-processing can match the download back to it.
