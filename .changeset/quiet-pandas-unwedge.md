---
"comicarr": patch
---

Fixed Retry and Search again doing nothing for an issue that had landed in needs-attention. Once an attempt ended in manual review, that issue was permanently blocked from that provider: the retry re-wanted the issue and started a search, and the search then refused to hand anything to the download client — so the item quietly bounced back into needs-attention on the next cycle, forever, with nothing in the log to say why. Resolving a needs-attention item now genuinely releases it, so the next search can grab it again, however many times you need. An item you have *not* resolved yet still blocks — it may be something your download client already has, and clearing it automatically would both hide it from you and download it twice — but the log now names the item and its reason instead of reporting an unexplained handoff failure.
