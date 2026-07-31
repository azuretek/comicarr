# Activity Center — UX model and event contract

Decision record for [Design live activity visibility and timeline](https://github.com/frankieramirez/comicarr/issues/424),
charted under [Wayfinder: Activity Center](https://github.com/frankieramirez/comicarr/issues/425).
Every product and seam choice below is closed on that map; this document consolidates
them for implementers. Do not re-litigate settled tickets — zoom the linked issue for
detail, evidence, and rejected alternatives.

**Grounding tree:** decisions were verified against the tree at `ced9e2c7` and later
amended only by later closed tickets on the same map.

---

## 1. Destination (what we are building)

Comicarr gains a plain-language **Activity Center**:

1. A **compact global status line** showing whether the app is busy, how much is in
   flight, and whether anything needs the operator.
2. An **Activity page timeline** — chronological, human-readable, live while open —
   as the landing surface on `/activity`, with existing Direct Downloads and Download
   History as drill-downs.
3. A durable **narrative event table** plus **derived** live projections from existing
   acquisition ledgers, published through one **write facade** onto the existing
   `EventBus` / SSE transport.

**Not** a raw-log viewer, not fabricated search percentages, and not a fold-in of
`ai_activity_log`.

---

## 2. Surface ownership

| Surface | Owns | Source of truth |
|---|---|---|
| **Wanted** | Intent (still leave on snatch). Live-and-sticky **annotation** from the latest `acquisition_run_items` row for that issue | Legacy `t_issues.Status == 'Wanted'` membership; annotation from ledger |
| **Timeline** (`/activity` landing) | Narrative of work + pinned **needs-attention** band | Narrative table (feed); `pipeline_journal` (band) |
| **Direct Downloads** (renamed Queue tab) | DDL-only provider detail (`t_ddl_info`) | Unchanged |
| **Download History** | Cross-provider history (`t_snatched`) | Unchanged |
| **Global status line** (`AppStatusBar`) | Quiet counts: library · api · in flight · optional attention | Derived ledgers only |

Decisions: [Decide what Wanted, Queue and Activity each own in the UI](https://github.com/frankieramirez/comicarr/issues/429),
amended by [Prototype the global one-line status indicator](https://github.com/frankieramirez/comicarr/issues/434)
(`in flight` includes active searches, not journal stages alone).

### Tabs on `/activity`

Order: **Timeline · Direct Downloads · Download History**. Timeline is the default
landing view. No new nav item; the status indicator clicks through to `/activity`.

### Needs-attention band

Pinned **above** the chronological feed. Population:

```sql
SELECT * FROM pipeline_journal
 WHERE stage IN ('failed', 'manual_review')
   AND (status IS NULL OR status NOT IN ('retried', 'ignored', 'imported'))
 ORDER BY updated_date DESC
```

- Work queue, not notice board: rows clear only when an operator action moves the item.
- Red + actions live **only** on the band; stream rows for the same trouble are muted
  history with **no** actions
  ([Decide how failure, retry and degraded states read in the timeline](https://github.com/frankieramirez/comicarr/issues/432)).
- Band coverage for download failures that never terminalized the journal is achieved by
  **writing** `journal.mark_failed` at those seams, not by widening the predicate
  ([Decide whether the needs-attention band covers journal-less failures](https://github.com/frankieramirez/comicarr/issues/457)).

### Operator exits (`failed` / `manual_review`)

Stage lattice is **never** rewritten by operator actions. R9 columns already on
`pipeline_journal` (`status`, `retry_count`, `next_retry_at`) carry resolution:

| Stage | Actions |
|---|---|
| `failed` | `[retry]` `[ignore]` |
| `manual_review` | `[import]` `[search again]` `[ignore]` |

- `retry` / `search again` re-want and call a scoped `search_issue`; stamp
  `status='retried'`; do not reset the failed journal row's stage.
- `ignore` → `AcquisitionIntent.IGNORED` + `status='ignored'`.
- `import` → existing validated `POST /api/downloads/process`; stamp
  `status='imported'` **only on success**.
- Same-provider retries can produce a byte-identical `release_key` and lose
  `record_transition`'s `won` guard — that bug must be fixed **before** `[retry]`
  ships ([Decide how an item exits manual_review and failed](https://github.com/frankieramirez/comicarr/issues/437)
  amendment from grouping).

`_try_reset_failed_attempt` stays as-is for genuine re-snatch; it is not the operator
path and is not extended to `manual_review`.

---

## 3. Authority rule (derived vs narrated)

> **Derived state is authoritative for every count and every current-state badge.
> Narrated events are authoritative for every timestamped row. No surface computes one
> from the other, and no query aggregates the narrative table.**

The line is **tense**: ledgers answer *what is true now*; the narrative table answers
*what happened, when*.

| Kind | Examples | Store |
|---|---|---|
| Derived | `N in flight`, `⚠ K need attention`, in-flight run progress (`17 of 42 resolved`), Wanted sticky annotations, open story headers while a story is open | `acquisition_run_items`, `acquisition_runs`, `pipeline_journal` |
| Narrated | Feed rows, closed story headers, run **completion** brackets | Narrative table only |

**Enforcement (greppable):** `COUNT(*)`, `GROUP BY`, or `WHERE status = <current>` over
the narrative table is always a bug. The table is only ever read as an ordered
time slice.

Implications:

- `download.started` does not exist — downloading is live state.
- Per-issue `search.no_match` does not narrate — Wanted annotation + run bracket.
- `degraded` / `retrying` narrate **nothing** — guard + Wanted annotation only.
- In-flight search progress is **derived**; completion is **narrated** past tense.
- Retention may delete a feed row while a band row remains — accepted; the band is
  self-contained.

Decision: [Draw the line between derived state and narrated events](https://github.com/frankieramirez/comicarr/issues/427).

---

## 4. Event vocabulary

Two axes: **`activity` × `status`**. Severity is a pure function of `status`.

### Activities (7)

| activity | Meaning |
|---|---|
| `search` | Provider sweep / run bracket |
| `grab` | Release accepted and handed to downloader |
| `download` | Transfer completed (or failed) |
| `import` | Post-processing / library placement |
| `refresh` | Metadata pulled from a provider |
| `add` | Series or arc enters the library |
| `tag` | Metatagger writing into archives (not `refresh`) |

No `system` activity (version-check, restart, shutdown stay off the timeline).

### Statuses and severity

| status | Severity |
|---|---|
| `started`, `succeeded`, `no_match`, `cancelled` | `normal` |
| *(no narrative `retrying` rows)* | `degraded` is a **guard** only |
| `failed`, `blocked`, `needs_attention` | `action_required` |

**`retrying` is withdrawn.** `next_attempt_at` is written nowhere; the real backoff is
an in-process sleep capped at 60s. Discriminator for “retry pending” (guard only):
`state = accepted AND attempt_count > 0`.

### Subjects

`issue` · `annual` · `series` · `arc` · `run`

### Legal cells (summary)

Original legality table from
[Pin the Activity event vocabulary](https://github.com/frankieramirez/comicarr/issues/426),
amended by later tickets:

- **`tag`** row: `started` / `succeeded` / `failed` / `needs_attention` @ `issue`|`series`
- Blessed: `refresh × arc`, `grab × cancelled`, `import × cancelled`, `download × cancelled`
- Dropped: per-issue `search.no_match`, all `retrying` cells, `search.blocked` @ `run` as a feed row
- Run brackets narrate **completion** (and “nothing to search” vs “searched, no results” split)
- Operator ignore → `cancelled` with `reason_code = ignored_by_operator` on the activity that was in trouble

Producers write **data, never prose**. Sentences render client-side.

### Reason fields

| Field | Role |
|---|---|
| `reason_code` | Enumerated token; **required** when severity ≠ `normal`; client lexicon → phrase |
| `reason_detail` | Nullable free text; expand-only; never the primary detail line |

Unmapped codes degrade to a generic phrase + expandable raw token — never a snake_case
token as the primary sentence.

### Field contract (narrative row / SSE payload)

| Field | Notes |
|---|---|
| `event_id` | PK |
| `created_at` | Feed order; indexed for retention |
| `activity`, `status` | Discriminators |
| `subject_type`, `subject_id`, `subject_label` | Label denormalized so history survives subject deletion |
| `reason_code`, `reason_detail` | As above |
| `provider` | When relevant |
| `run_id` | **Search only** — removed from grab (grouping + seam unimplementable) |
| `release_key` | Required on `download` / `import` (journal join), not the grouping key |
| `parent_series_id` | Denormalized at write for series-scoped filters |
| `scope_type`, `scope_id` | On `run` subjects when the run is scoped |

---

## 5. Story grouping

The group is the **story of one subject**, not a batch / `run_id`.

| Rule | Value |
|---|---|
| Identity | `(subject_type, subject_id)` |
| Opens on | `grab.succeeded`, `download.succeeded`, `import.started`, `tag.started` |
| Closes on | Allowlist of terminal pairs (mirrors journal `TERMINAL_STAGES` spirit) — not “anything that isn’t an advance” |
| Retry | Opens a **second** story; never reopens the first |
| Collapse | **Always** collapsed; group-of-one degenerates to a plain row |
| Position | Opening row’s `created_at`; **nothing re-sorts** |
| Open header | Derived from `pipeline_journal.stage` (max rank across concurrent attempts) |
| Closed header | Terminal event’s own sentence |
| Trouble | Non-`normal` events are closing events → headers; never trapped interior rows |

Decision: [Decide grouping and collapse rules for the timeline](https://github.com/frankieramirez/comicarr/issues/428).
Prototype asset (throwaway): branch `prototype/timeline-view` — **Variant A (Ledger)**
won ([Prototype the timeline view](https://github.com/frankieramirez/comicarr/issues/435)).

### Timeline chrome (Variant A)

- Absolute `HH:MM` mono gutter, severity mark (6px dot: green open story, red closed-in-trouble, else none), sentence with inline entity link, `RelativeTime` right.
- **No** per-row `StatusPill`.
- Paginated **25** stories (not infinite scroll, not windowed).
- Sticky day rules (`TODAY` / `YESTERDAY` / weekday+date).
- Empty: `EmptyState` instead of toolbar; “Add a series” action.
- **Filters that ship:** free-text over subject/sentence fields, and **activity** dropdown. The prototype’s needs-attention toggle does **not** ship — the band is the attention surface. Scope arrives via query params (below).

---

## 6. Scoped timeline slices

Scoped views are **filters of Activity only** — no embedded feed on series/issue pages.

```
GET /api/activity/timeline?scope_type=issue|annual|series&scope_id=<id>
```

- Issue/annual: exact subject match.
- Series: rollup via `parent_series_id` + series subject rows + series-scoped run events.
- When scoped, the band is the open-trouble predicate **intersected** with that scope.
- Deleted subjects: scoped deep-link empty/soft-404; global keeps `subject_label` history.
- Detail pages deep-link only, e.g. `/activity?scope_type=series&scope_id=…`.

Decision: [Decide whether series and issue pages get scoped timeline slices](https://github.com/frankieramirez/comicarr/issues/438).

---

## 7. Producer contract and `GLOBAL_MESSAGES`

### Facade

One **publish facade** owns narrative insert + SSE publish (precedent: `ai/service.py`
`log_activity`, corrected):

1. Narrative row **co-commits** into the caller’s transaction when `conn` is supplied.
2. Publish **after commit**, never before durability.
3. Gate journal-backed publishes on `record_transition`’s **`won`** return (idempotent under concurrency).
4. Publish is **best-effort** (no outbox) — the list is query-backed.
5. Enforce legal cells and `reason_code` invariants at this choke point.

### Wire

- Single SSE event type: **`activity`**, payload = typed row (`activity`/`status` discriminators).
- Timeline list is **query-backed**; stream **invalidates**, never accumulates.
- `EventBus` left unchanged (drop-oldest is correct under query-backed lists).

### Ledger hygiene (same effort)

- `record_outcome` / `record_requeue` run reasons through
  `comicarr.app.common.redaction.redact_sensitive_text`.
- `record_requeue(..., replay=False)`; facade publishes only when not replay; replay sites pass `replay=True`.
- `pipeline_journal.fail_reason` is token-only; exception text goes to sanitised detail
  (fix the one concatenating site at `downloads/service.py`).

### `GLOBAL_MESSAGES` retirement

~31 production write sites. Each conversion **deletes** its `GLOBAL_MESSAGES` write in
the **same** issue that adds its event. Final cleanup removes the declaration,
`global` entry, dead client handlers, and lands a **CI guard** (attribute assignment
cannot be made to fail by deleting the declaration). Contributor-only guard → document
in `CLAUDE.md`, **no changeset**.

`versioncheck` write is owned by the update-notification map (already sliced), not here.

Decision: [Settle the event producer contract and the fate of GLOBAL_MESSAGES](https://github.com/frankieramirez/comicarr/issues/430).

### Package seam

New domain package **`comicarr/app/activity/`** (facade, queries, router, retention).
Wire the router from `comicarr/app/main.py`. Do not hang narrative ownership off
`downloads` or `series`.

Table name: **`activity_events`**.

---

## 8. Live updates, reconnect, toasts

### Delivery

| Concern | Rule |
|---|---|
| Gap recovery | Refetch only — no `Last-Event-ID` / stream resume |
| Invalidation | Coalesce/debounce all narrative **and** derived keys on `activity` |
| Brief disconnect | Silent; keep last good query data |
| Prolonged loss | Status chrome `unreachable` (wire existing `isConnected` / `isReconnecting`) |
| Fallback poll | Permanent **30s** under SSE |
| Backoff | Keep 64s cap; visibility/focus → immediate reconnect |
| Multi-tab | Per-tab EventSource accepted |

Decision: [Decide live-update delivery, reconnect and fallback for an open timeline](https://github.com/frankieramirez/comicarr/issues/431).

### Toasts

One envelope, two consumers:

| Severity | SSE interrupt toast |
|---|---|
| `action_required` | Yes, subject to **enter-trouble session latch** |
| `degraded` / `normal` | Never |

Latch clears when open trouble the client can see is gone. Local mutation acks stay a
separate layer. Handler disposition table lives on
[Decide the relationship between toasts and the timeline](https://github.com/frankieramirez/comicarr/issues/439)
(`addbyid` / `storyarc_added` rewire; `search_*`, `scheduler_message`, `config_check`,
generic `message` delete; `shutdown`/`restart`/`ai_activity` keep).

---

## 9. Global status indicator

**Variant A — quiet counts** (prototype `prototype/global-status-indicator`):

```
library: N series · api: online · M in flight
library: N series · api: online · M in flight · ⚠ K need attention
library: N series · api: online · idle
library: unavailable · api: offline · unreachable
```

| Number | Query |
|---|---|
| `M in flight` | `COUNT(acquisition_run_items WHERE state IN ('accepted','running'))` **+** `COUNT(pipeline_journal WHERE stage IN OPEN_STAGES)` |
| `K need attention` | Same unresolved band predicate as the Timeline band |
| `idle` | both open-work counts zero and attention zero |

- Shared app SSE invalidates status React Query; **30s poll** remains; **no** second EventSource.
- Single click on activity/attention text → `/activity`.
- `aria-live` only for offline/recovery, attention appear/change/clear, idle↔busy — not count ticks.

Decision: [Prototype the global one-line status indicator](https://github.com/frankieramirez/comicarr/issues/434).

---

## 10. Retention

| Concern | Decision |
|---|---|
| Predicate | Age only: `DELETE WHERE created_at < now - 90 days` |
| Count ceiling | No |
| Severity tier | No |
| Job | Own daily `_add_recurring_job` + `SCHEDULER_JOB_NAMES` entry |
| Config key | No (constant; promote later if needed) |
| Manual purge | No |
| Index | Required on `created_at` |
| Scope | Narrative table **only** |

Five existing unbounded ledgers are a **separate** map:
[Wayfinder: Ledger retention](https://github.com/frankieramirez/comicarr/issues/458).

Decision: [Decide retention for the narrative event table](https://github.com/frankieramirez/comicarr/issues/433).

---

## 11. Explicitly not being built

Carried from the map’s Out of scope and closed tickets:

- Raw-log viewer / streaming `comicarr.log`
- Progress percentages or ETAs for searches; fabricated download progress
- Folding `ai_activity_log` into this timeline
- Retention for the five existing unbounded ledgers (→ #458)
- Manual “clear timeline”
- System notices in the timeline (version / restart / shutdown)
- Stall classifier / age-based open-stage band membership
- Embedded timeline on series/issue detail pages
- Changing the Wanted membership rule (still leaves on snatch)
- Replacing Direct Downloads content (rename + honesty only)
- Self-apply / update toast path (other map)

---

## 12. Implementation issues (dependency order)

Sliced by [Slice the approved design into implementation issues](https://github.com/frankieramirez/comicarr/issues/436).
Native GitHub `blocked_by` edges are the UI-visible frontier; the graph below is the index.

```
[477] Activity narrative table migration and indexes
  ├─► [479] Activity event write facade
  │     └─► [484] Wire producers + retire GLOBAL_MESSAGES writes
  │           └─► [488] Live updates, toast latch, dead SSE cleanup
  ├─► [485] Timeline, band, and open-work read APIs
  │     ├─► [486] Timeline UI + detail deep-links  (also ← 483)
  │     └─► [487] Global quiet-counts status indicator
  │           └─► [488] (also ← 484, 486)
  └─► [489] 90-day retention job

[482] Complete pipeline_journal terminals for failed-download paths
  └─► [483] Needs-attention band resolution actions  (also ← 477)
        └─► [486]

[490] Wanted live-sticky acquisition annotations   (unblocked)
```

**Frontier (can start now):** [#477](https://github.com/frankieramirez/comicarr/issues/477),
[#482](https://github.com/frankieramirez/comicarr/issues/482),
[#490](https://github.com/frankieramirez/comicarr/issues/490).

| # | Title | Changeset? | Blocked by |
|---|---|---|---|
| [#477](https://github.com/frankieramirez/comicarr/issues/477) | Activity narrative table migration and indexes | **No** (schema only) | — |
| [#479](https://github.com/frankieramirez/comicarr/issues/479) | Activity event write facade | **No** (internal) | 477 |
| [#482](https://github.com/frankieramirez/comicarr/issues/482) | Complete pipeline_journal terminals for failed-download paths | **Yes (patch)** | — |
| [#483](https://github.com/frankieramirez/comicarr/issues/483) | Needs-attention band resolution actions | **Yes (minor)** | 482, 477 |
| [#484](https://github.com/frankieramirez/comicarr/issues/484) | Wire activity producers and retire GLOBAL_MESSAGES writes | **No** if before UI; **yes (minor)** if feed already visible | 479, 482 |
| [#485](https://github.com/frankieramirez/comicarr/issues/485) | Activity timeline, band, and open-work read APIs | **No** (API-only) | 477 |
| [#486](https://github.com/frankieramirez/comicarr/issues/486) | Activity Center timeline UI and detail deep-links | **Yes (minor)** | 485, 483 |
| [#487](https://github.com/frankieramirez/comicarr/issues/487) | Global activity status indicator (quiet counts) | **Yes (minor)** | 485 |
| [#488](https://github.com/frankieramirez/comicarr/issues/488) | Activity live updates, toast latch, and dead SSE cleanup | **Yes (patch)**; CI guard no changeset | 484, 486, 487 |
| [#489](https://github.com/frankieramirez/comicarr/issues/489) | Activity narrative 90-day retention job | **No** | 477 |
| [#490](https://github.com/frankieramirez/comicarr/issues/490) | Wanted page live-sticky acquisition annotations | **Yes (minor)** | — |

*Practical call for producers:* prefer **one** minor changeset on the first
operator-visible PR that makes the feed real (usually timeline UI after producers).

### Shape vs the terminal ticket’s rough list

| Expected rough slice | Issue(s) |
|---|---|
| Migration + table | #477 |
| Write facade and seams | #479 |
| EventBus producer wiring + GLOBAL_MESSAGES retirement (writes) | #484 |
| Read endpoints | #485 |
| Timeline components | #486 |
| Status indicator | #487 |
| Retention job | #489 |
| Dead-client-handler cleanup | #488 (with live/toast) |
| **Added from closed decisions** | #482 journal terminals (#457); #483 band actions (#437); #490 Wanted annotations (#429); deep-links folded into #486 (#438) |

### Prototype assets (rewrite; do not merge branches)

- `prototype/timeline-view` — layout, day rules, collapse chrome, `stories` grouping helper
- `prototype/global-status-indicator` — quiet-count format + scenes

---

## 13. Decision index

| Ticket | Gist |
|---|---|
| [#429](https://github.com/frankieramirez/comicarr/issues/429) | Surface ownership; band; tabs; status line shape |
| [#426](https://github.com/frankieramirez/comicarr/issues/426) | Vocabulary axes; severity; subjects; sentences |
| [#427](https://github.com/frankieramirez/comicarr/issues/427) | Tense line; authority rule; reason_code/detail |
| [#432](https://github.com/frankieramirez/comicarr/issues/432) | Loud once; no retrying rows; honesty boundary |
| [#430](https://github.com/frankieramirez/comicarr/issues/430) | Facade; wire; GLOBAL_MESSAGES; tag; guards |
| [#437](https://github.com/frankieramirez/comicarr/issues/437) | R9 exits; band predicate; same-provider retry note |
| [#433](https://github.com/frankieramirez/comicarr/issues/433) | 90-day age retention; own job; no knob |
| [#428](https://github.com/frankieramirez/comicarr/issues/428) | Subject stories; always collapsed |
| [#457](https://github.com/frankieramirez/comicarr/issues/457) | Journal-complete failed paths for band coverage |
| [#438](https://github.com/frankieramirez/comicarr/issues/438) | Scoped Activity filters; deep-links only |
| [#439](https://github.com/frankieramirez/comicarr/issues/439) | Toast latch; handler disposition |
| [#434](https://github.com/frankieramirez/comicarr/issues/434) | Quiet counts status indicator |
| [#435](https://github.com/frankieramirez/comicarr/issues/435) | Ledger timeline chrome (Variant A) |
| [#431](https://github.com/frankieramirez/comicarr/issues/431) | Invalidate + 30s poll; no stream resume |
| [#436](https://github.com/frankieramirez/comicarr/issues/436) | This slice + ADR |

---

## 14. Acceptance against #424

| Criterion | Where |
|---|---|
| Decision record defines UX model and event contract | This document |
| Names data / source-of-truth path | §§2–3, 7 |
| Implementation slices and dependencies | §12 + linked issues |
