# Acquisition Recovery Runbook

Use this runbook to deploy the acquisition recovery release and repair a
migrated series without silently requeueing ambiguous work. It is deliberately
stop-safe: an unexpected count, unverified build, active external side effect,
or stale preview is a **NO-GO**, not a reason to retry with a wider scope.

This is an operator procedure, not an API-key workflow. All mutation endpoints
below require the current owner browser session and the
`X-Requested-With: ComicarrFrontend` header. Prefer the Settings UI for normal
operation. If an API example is needed, use an approved local cookie jar with
mode `0600`; never paste a production session cookie or API key into a shell
history, ticket, or chat.

## Record owners and evidence first

Do not begin until these people and the evidence location are written down.

| Responsibility | Named owner | Evidence location |
| --- | --- | --- |
| Image/container deployment | _fill in_ | _fill in_ |
| Database backup and restore | _fill in_ | _fill in_ |
| Repair-preview review and apply approval | _fill in_ | _fill in_ |
| Downloader/client and file-side-effect review | _fill in_ | _fill in_ |
| Rollback decision | _fill in_ | _fill in_ |

Create a dated working directory that is not inside Comicarr's data directory.
It should contain the JSON responses, backup checksum, image digest, screenshot
or export of downloader jobs, and the repair/canary IDs recorded below.

```sh
export BASE='https://comicarr.example.invalid' # use the operator-facing HTTPS URL
export WORK="$HOME/comicarr-recovery-$(date +%F-%H%M%S)"
export COOKIE_JAR="$WORK/owner.cookies"
mkdir -p "$WORK"
chmod 700 "$WORK"
```

The examples assume `COOKIE_JAR` already represents the **same current owner
session** that created a preview. Do not use `-k` to bypass TLS validation.

```sh
owner_get() {
  curl --silent --show-error --fail-with-body --cookie "$COOKIE_JAR" "$BASE$1"
}

owner_post() {
  curl --silent --show-error --fail-with-body --cookie "$COOKIE_JAR" \
    --header 'Content-Type: application/json' \
    --header 'X-Requested-With: ComicarrFrontend' \
    --data "$2" "$BASE$1"
}
```

## Go/no-go gates

### 1. Prove the deployed image, not just its tag

The fixed container must be built with both `COMICARR_BUILD_ID` and
`COMICARR_BUILD_COMMIT`. A version string, a branch label, or a runtime Git
fallback is diagnostic context only; it is not release proof.

```sh
owner_get /api/system/version | tee "$WORK/version.json"
jq -e '
  .build.verified == true and
  (.build.id | type == "string" and length > 0) and
  (.build.commit | type == "string" and length >= 7)
' "$WORK/version.json" >/dev/null
```

Record the image digest and the exact `build.id` / `build.commit`. If this
command fails, stop: rebuild/redeploy the image with both build arguments and
repeat the check.

### 2. Prove a complete route before suppression

Before turning on maintenance, capture route readiness. At least one route must
be end-to-end ready (provider, compatible downloader, destination path, and
restart correlation), not merely configured.

```sh
owner_get /api/search/health | tee "$WORK/health-before-maintenance.json"
jq -e '.viable_route == true' "$WORK/health-before-maintenance.json" >/dev/null
```

After maintenance is enabled, `viable_route` is expected to become false
because the maintenance gate deliberately suppresses routes. Preserve the
pre-maintenance result; do **not** treat that expected suppression as a broken
route or remove the gate to make the value true.

### 3. Capacity, correlation, and backup readiness

Before any mutation, require all of the following:

- At least three times the database size free and at least 10% free space on
  the relevant volume.
- No unowned in-flight downloader job, journal row, DDL entry, or file move.
  Ambiguous work is manual review; it is never a blind requeue.
- A restore operator and engine-specific restore procedure.
- For SQLite, a WAL-safe independent backup. Copying only the live `.db` file
  is not a backup while WAL is in use.

For SQLite, use the SQLite backup API (or an equivalent Synology-supported
snapshot), then independently open the result. Replace the paths with the
actual mounted database and out-of-volume backup location.

```sh
sqlite3 "$LIVE_DB" ".backup '$BACKUP_DB'"
sqlite3 "$BACKUP_DB" 'PRAGMA integrity_check;'
shasum -a 256 "$BACKUP_DB" | tee "$WORK/backup.sha256"
```

Record and compare key-table counts from the live database and independent
backup. Use engine-native snapshot/verification for PostgreSQL or MySQL.

```sh
for table in comics issues annuals acquisition_runs acquisition_run_items; do
  printf '%s=' "$table"
  sqlite3 "$BACKUP_DB" "SELECT count(*) FROM $table;"
done | tee "$WORK/backup-counts.txt"
```

Any integrity failure, count mismatch, or unexplained in-flight work is a
**NO-GO**.

## Phase 0 — Start the fixed release with automatic work suppressed

1. Set `COMICARR_ACQUISITION_MAINTENANCE=1` on the fixed container before it
   starts. Stop the previous container first if that is necessary to change its
   environment.
2. Start the fixed image with the gate still enabled.
3. Re-run the build proof above. Capture search health and require the gate to
   be visible:

   ```sh
   owner_get /api/search/health | tee "$WORK/health-maintenance-a.json"
   jq -e '.maintenance.blocked == true' "$WORK/health-maintenance-a.json" >/dev/null
   sleep 30
   owner_get /api/search/health | tee "$WORK/health-maintenance-b.json"
   jq -e '.maintenance.blocked == true' "$WORK/health-maintenance-b.json" >/dev/null
   ```

4. Between the two samples, compare the following external and durable facts:
   acquisition run IDs and provider attempts, journal-stage counts, DDL
   timestamps, and downloader-client job lists. They must not advance. If a
   claim, submission, or move advances, stop and investigate the gate before
   taking a backup or applying a repair.

## Phase 1 — Capture the read-only baseline

Save the following in `WORK` before repair:

- image digest and verified build JSON;
- database engine, location, schema/version, integrity result, and free-space
  calculation;
- issue status / NULL / date / location counts, `Have` / `Total`, and Wanted
  counts;
- acquisition run states, journal stages and malformed payloads;
- legacy DDL age/correlation, snatch/nzblog orphans, and downloader jobs;
- `GET /api/search/health`, `GET /api/system/migration/progress`, and any
  active repair/canary state.

The baseline makes later rollback decisions evidence-based. It is not optional
even when the first target is only one series.

## Phase 2 — Repair Absolute Batman (`160294`) from a current preview

Keep maintenance enabled. The repair preview is read-only, session-bound, and
expires after 15 minutes. Do not change browsers or log out between preview and
confirm.

```sh
owner_post /api/system/acquisition/repair/preview '{"series_id":"160294"}' \
  | tee "$WORK/absolute-batman-preview.json"
```

For the reported Absolute Batman condition, the preview must show exactly:

| Evidence/proposal | Required count |
| --- | ---: |
| Verified file-backed owned | 18 |
| Released optional Wanted candidates | 2 |
| Future/deferred | 2 |
| Automatic legacy requeues | 0 |
| Automatic explicit-intent changes | 0 |

Check the whole manifest, not only the summary. The following is a useful
mechanical gate; manual review of every selected item is still required.

```sh
jq -e '
  .summary.owned == 18 and
  .summary.optional_wanted == 2 and
  .summary.future == 2 and
  ([.items[] | select(.selected and .proposed_values.Status? == "Wanted")] | length) == 0 and
  ([.items[] | select(.evidence.explicit_intent == true and (.proposed_values | length > 0))] | length) == 0
' "$WORK/absolute-batman-preview.json" >/dev/null
```

If any count or selected entity is surprising, stop. Do not alter future,
paused, unknown, archived, ignored, or explicitly skipped rows merely to make
the screenshot look complete.

Select only the two optional released-missing rows. Their `entity_key` values
are immutable `issue:<id>` or `annual:<id>` identifiers from the preview—not
issue numbers typed by hand.

```sh
export REPAIR_RUN_ID="$(jq -r '.run_id' "$WORK/absolute-batman-preview.json")"
export PREVIEW_TOKEN="$(jq -r '.preview_token' "$WORK/absolute-batman-preview.json")"
export PREVIEW_FINGERPRINT="$(jq -r '.fingerprint' "$WORK/absolute-batman-preview.json")"
export OPTIONAL_KEYS="$(jq -c '[.items[] | select(.optional and .reason == "released_missing" and .proposed_values.Status? == "Wanted") | .entity_key]' "$WORK/absolute-batman-preview.json")"

test "$(jq 'length' <<<"$OPTIONAL_KEYS")" -eq 2
owner_post "/api/system/acquisition/repair/$REPAIR_RUN_ID/confirm" \
  "$(jq -cn \
    --arg token "$PREVIEW_TOKEN" \
    --arg fingerprint "$PREVIEW_FINGERPRINT" \
    --argjson selected "$OPTIONAL_KEYS" \
    '{preview_token:$token, fingerprint:$fingerprint, selected_optional_keys:$selected}')" \
  | tee "$WORK/absolute-batman-confirm.json"
```

`409` means the preview expired, belonged to another session, was consumed, or
went stale. It is safe to create a fresh preview; it is not safe to reuse the
old token or fingerprint.

Apply only that immutable manifest. Apply creates no downloader submission.

```sh
owner_post "/api/system/acquisition/repair/$REPAIR_RUN_ID/apply" '{}' \
  | tee "$WORK/absolute-batman-apply.json"
owner_get "/api/system/acquisition/repair/$REPAIR_RUN_ID" \
  | tee "$WORK/absolute-batman-run.json"

jq -e '.run.state == "completed" and .run.conflict_count == 0' \
  "$WORK/absolute-batman-run.json" >/dev/null
```

If the run waits for drain, stays applying, or reports a conflict, leave the
gate in place and poll the run. Do not start a second repair. A conflict is a
manual-review result, not a failed retry.

Create a fresh convergence preview after successful apply. It must contain no
automatic proposed mutation; preserve its JSON as the after-state evidence.

```sh
owner_post /api/system/acquisition/repair/preview '{"series_id":"160294"}' \
  | tee "$WORK/absolute-batman-convergence.json"
jq -e '([.items[] | select(.proposed_values | length > 0)] | length) == 0' \
  "$WORK/absolute-batman-convergence.json" >/dev/null
```

## Phase 3 — Canary authorization boundary (not a full production canary)

The repair manifest and a downloader canary are distinct controls. The repair
must already be `completed` with zero conflicts before an external-handoff
permit can be authorized. Automatic work remains suppressed throughout this
phase.

Only a restart-safe route is valid for the current permit: `sabnzbd`, `nzbget`,
`ddl`, `rtorrent`, or `deluge`. The `release_key` must be the exact
provider-release identity that the normal acquisition path would submit; never
substitute an issue ID, title, or guessed downloader ID.

**Current release limitation — production NO-GO:** this API authorizes exactly
one already-known external handoff, but it does not persist/select a provider
candidate, enqueue a search, or invoke the downloader. General search claims
remain fenced. Consequently it cannot prove the required
search → reservation → acceptance → download → owned canary while maintenance
is active. Do not release maintenance or invoke a bulk/force search to work
around this boundary.

A future release needs a dedicated, persisted-candidate executor that can
consume exactly one reviewed candidate under the permit and return its durable
run/journal/client/file outcome. Until that exists and is tested, record the
authorization contract below as a limitation; do **not** claim a successful
production canary or proceed to broad automatic resume on its basis.

The following API sequence is useful only for inspecting and cancelling an
unclaimed permit (or for a delivery-tested internal handoff path). It must use
the same owner session:

```sh
export RELEASE_KEY='exact durable provider release key'
export ROUTE='sabnzbd'
owner_post "/api/system/acquisition/repair/$REPAIR_RUN_ID/canary" \
  "$(jq -cn --arg release_key "$RELEASE_KEY" --arg route "$ROUTE" '{release_key:$release_key, route:$route}')" \
  | tee "$WORK/canary-authorize.json"
export CANARY_PERMIT_ID="$(jq -r '.permit_id' "$WORK/canary-authorize.json")"

owner_get "/api/system/acquisition/canary/$CANARY_PERMIT_ID" \
  | tee "$WORK/canary-poll.json"
```

`authorized` means no external request has happened. `claimed` means a single
delivery-tested handoff path is in progress; wait for a terminal result.
`completed` means that handoff path recorded a terminal outcome, not that this
release has independently proven a full production acquisition. A future
executor must capture the permit ID, matching search run ID, exact release key,
client acceptance identity, journal stage, file move, and resulting owned state
with one submission and one move.

Release the fence after inspection. Releasing an unclaimed `authorized` permit
is an audited cancellation; releasing `completed` ends the permit fence. A
`claimed` permit cannot be released while its lease is active.

```sh
owner_post "/api/system/acquisition/canary/$CANARY_PERMIT_ID/release" \
  '{"reason":"canary outcome recorded in recovery evidence"}' \
  | tee "$WORK/canary-release.json"
```

If a delivery-tested handoff has an ambiguous submission, duplicate, missing
client identity, or missing file/ownership transition, freeze the instance and
follow the post-acceptance rollback boundary below. Do not cancel-and-resubmit
blindly.

## Phase 4 — Reconciliation and abandoned-maintenance recovery

Mylar migration is not complete merely because rows were copied. Its durable
reconciliation state survives restart:

```sh
owner_get /api/system/migration/progress | tee "$WORK/migration-progress.json"
```

`pending_preview` or `failed` keeps acquisition blocked until an operator has
reviewed the repair evidence. `migrating` means wait. Do not mark acquisition
ready while a maintenance fence is active or a migration is running.

After repair evidence is complete and all persistent fences have been released,
an operator can record the migration/reconciliation review:

```sh
owner_post /api/system/acquisition/reconciliation/ready \
  '{"reason":"Absolute Batman preview, repair, and backup evidence reviewed"}' \
  | tee "$WORK/reconciliation-ready.json"
```

This endpoint records an audited gate transition; it does not excuse an
unexpected preview, external side effect, or unresolved repair conflict. In
this release it also does **not** satisfy the missing full-canary proof: keep
`COMICARR_ACQUISITION_MAINTENANCE=1` in place and do not treat `ready` as
authorization for broad production resume.

Use the maintenance-abort endpoint only to recover an abandoned persistent
fence, never as normal completion. First prove from health, journal, and the
downloader client that there are **zero active leases and no active side
effect**. Then record why the original owner cannot finish it:

```sh
owner_get /api/search/health | tee "$WORK/health-before-maintenance-abort.json"
# Require .maintenance.active_leases == 0 and independently verify the client.
owner_post /api/system/acquisition/maintenance/abort \
  '{"reason":"owner unavailable; no active lease or downloader job after evidence review"}' \
  | tee "$WORK/maintenance-abort.json"
```

An abort releases only the fence. It does not make an incomplete repair valid,
does not alter reconciliation state, and does not make a pre-existing side
effect safe to retry. Poll the repair, resolve/rollback it conditionally, or
create a new preview as appropriate before resuming.

## Phase 5 — Staged resume and observation (after the missing canary executor ships)

The current release cannot satisfy the production canary proof above. Keep
automatic acquisition suppressed or roll back at a safe boundary until the
dedicated persisted-candidate executor is available and has passed the exact
controlled-acquisition checks. Do not use this phase to bypass that release
limitation.

Once that executor exists and its one-item canary succeeds, use this sequence:

1. Confirm no canary/repair/migration fence or lease remains, and save health.
2. Remove `COMICARR_ACQUISITION_MAINTENANCE=1` from the container definition
   and restart the fixed image. A non-ready durable reconciliation state still
   blocks claims after restart, so this is not an automatic broad resume.
3. Verify `GET /api/search/health` shows an unblocked maintenance projection
   and at least one viable route. If reconciliation was pending, make the
   explicit `reconciliation/ready` call above only after that check.
4. Resume in this order, recording run IDs and terminal outcomes after each:
   recovery/monitor, metadata jobs, a five-item manually reviewed Wanted batch,
   then Auto-Search. Do not turn on Auto-Search merely because a scheduler
   dispatch is accepted.
5. Observe and retain health at +5 minutes, +1 hour, after the first six-hour
   search cycle, and +24 hours.

Re-enter maintenance immediately for an uncaught worker exception, duplicate
submission or move, unaccounted queue item, stale Running state, unexpected
Unknown/quarantine growth, repair conflict, or missing terminal acquisition
outcome.

## Rollback by side-effect boundary

| Boundary | Permitted action |
| --- | --- |
| Before repair apply | Previous image plus verified snapshot may be restored only after schema compatibility is assessed. |
| After repair, before downloader acceptance | Stop every writer, use the verified snapshot or conditional manifest rollback, then validate journal/outbox state. |
| After downloader acceptance or file move | **Database-only rollback is forbidden.** Freeze, preserve the release/client/file correlation, cancel or complete the external job, inventory files, then choose a coordinated restore or conditional manifest rollback. |

For a completed repair with no external side effect, conditional rollback is
available only when source rows still match the recorded applied values. It may
report conflicts; a conflict must be reviewed rather than overwritten.

```sh
owner_post "/api/system/acquisition/repair/$REPAIR_RUN_ID/rollback" \
  '{"reason":"pre-acceptance rollback approved by rollback owner"}' \
  | tee "$WORK/repair-rollback.json"
```

For SQLite restore, stop every writer, restore the verified database as a unit,
and never mix old `-wal`/`-shm` files with the restored snapshot. Re-run
`PRAGMA integrity_check`, journal/outbox checks, route health, and the
maintenance/reconciliation gates before resuming anything.

## API quick reference

| Purpose | Endpoint and required payload |
| --- | --- |
| Build proof | `GET /api/system/version` → require `build.verified: true` |
| Route/maintenance health | `GET /api/search/health` |
| Migration reconciliation | `GET /api/system/migration/progress` |
| Series bulk-search preview | `GET /api/series/{id}/search-missing/preview` |
| Series bulk-search confirm | `POST /api/series/{id}/search-missing` with `confirm`, `preview_token`, and `fingerprint` from the same session |
| Repair preview | `POST /api/system/acquisition/repair/preview` with `series_id` |
| Repair confirm | `POST /api/system/acquisition/repair/{run_id}/confirm` with `preview_token`, `fingerprint`, and explicit `selected_optional_keys` |
| Repair apply/poll/rollback | `POST .../{run_id}/apply`, `GET .../{run_id}`, `POST .../{run_id}/rollback` with a reason |
| Canary authorize/poll/release | `POST .../{run_id}/canary` with exact `release_key` and `route`; `GET /api/system/acquisition/canary/{permit_id}`; `POST .../{permit_id}/release` with a reason. This release authorizes/cancels a handoff only; it does not execute a full production canary. |
| Explicit reconciliation release | `POST /api/system/acquisition/reconciliation/ready` with a reason |
| Audited abandoned-fence recovery | `POST /api/system/acquisition/maintenance/abort` with a reason and only after all leases drain |

Repair, canary, reconciliation, and maintenance-abort APIs reject API-key-only
callers. They must be made from the owner session that owns the associated
preview or permit.
