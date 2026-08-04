---
"comicarr": minor
---

The needs-attention band no longer asks you to babysit failures Comicarr can handle itself. After a restart, downloads that vanished from the client, bad DDL links, and similar dead ends are returned to the acquisition cycle automatically — blocklisted when the release is gone, re-wanted so the next sweep can find a different source — instead of stacking up as hundreds of red cards you can only "retry" by hand.

What still needs you stays on the band: files that downloaded but never made it into the library, downloads waiting on a decision only you can make, and failures where you turned auto-handling off. Those still group by series and cause, still open the Needs attention page, and still clear only when you act.

Under the hood every failure reason is classified once, in code. New reasons have to declare whether they belong on the band before they can merge, so the next bulk failure can't recreate the old pile.
