# ADR-0001: Needs-attention band actionability

**Status:** Accepted  
**Date:** 2026-08-04  
**Issues:** [#523](https://github.com/frankieramirez/comicarr/issues/523), [#541](https://github.com/frankieramirez/comicarr/issues/541)  
**Map:** [Wayfinder: Needs-attention band contract](https://github.com/frankieramirez/comicarr/issues/520)

## Context

The needs-attention band is a work queue: rows clear only by operator action
([activity-center.md](../architecture/activity-center.md)). That invariant
prevents silent age-based eviction of genuine trouble.

Admission, however, had no membership test. Every `failed` / `manual_review`
row with an unresolved status entered the band — including bulk
restart-replay artefacts (`download_gone`, …) where no operator action does
anything the system cannot do itself. Production showed hundreds of such rows
pushing the Activity timeline off the page.

A denylist of one token would leave the real defect intact: the next bulk
terminal reason would reproduce the leak.

## Decision

Band admission is governed by a **two-clause actionability test**:

1. **Admission.** Admit a row only when resolving it requires information,
   authority, or judgement the **operator** holds and the **system** does not.
2. **Exclusion.** A reason may be excluded only if the system **reconciles the
   item** — re-wanting it into the acquisition cycle, and blocklisting the
   release when the release (not just the attempt) is dead. Never leave the
   issue at `Status='Snatched'` with nothing watching.

Classification is exhaustive over the 22 known `fail_reason` **base tokens**
(substring before the first `:`), stored in
`comicarr/app/activity/reasons.py` beside operator phrases:

- 14 admitted (bytes stranded · external ambiguity · operator asked to be asked)
- 8 excluded, each with a recorded reconciliation obligation

Unknown tokens are **admitted (fail-open)** at runtime. Completeness is
enforced in CI (`scripts/check_fail_reason_registry.py` under `lint:guards`),
not by the predicate — fail-closed would strand the first unregistered writer.

The live predicate is one portable clause on `unresolved_band_condition()`:

```python
actionable_reason_condition(pipeline_journal.c.fail_reason)
```

No schema column, no migration: the band is computed live; changing admission
drops rows on deploy. A one-shot re-want/blocklist pass at recovery boot
handles issues stranded before this ADR shipped.

## Consequences

- The work-queue invariant **survives**: rows still clear only by action. What
  changes is *who is admitted* into the queue.
- Excluded trouble remains visible on the muted timeline and Download History;
  there is no second "quieter problems" tier.
- Writers of excluded reasons must call
  `comicarr.app.activity.reconcile.reconcile_excluded` (or already reconcile,
  as `download_failed_researching` does in `failed.py`).
- New `fail_reason` writers fail `npm run lint` until classified in `reasons.py`.
- `activity-center.md` documents the widened predicate; this ADR is the
  decision record for rewriting admission underneath the invariant.

## Rejected alternatives

| Alternative | Why rejected |
|---|---|
| `download_gone` denylist only | Leaves admission without a membership test |
| `needs_operator` journal column | Migrates and backfills what the base token already declares |
| Age-based eviction | Silently drops genuine `manual_review` trouble |
| Fail-closed unknown tokens | Strands `Snatched` issues with no reconciliation path |
| Conditional admit when artifact exists on disk | Per-row FS stats on every poll; band and status count can disagree |
| Operator-configurable classification | Exclusion carries code-only reconciliation obligations |
