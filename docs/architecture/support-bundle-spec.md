# Support bundle specification

**Status:** Locked  
**Date:** 2026-08-09  
**Contract version:** 1  
**Owner:** Comicarr maintainers  
**Map:** [Wayfinder: specify the Support bundle](https://github.com/frankieramirez/comicarr/issues/599)  
**Originating report:** [No CarePackage button in the UI](https://github.com/frankieramirez/comicarr/issues/590)

Implementation is a **separate handoff** tracked on the originating report. This document is the human entry point for the checked-in contract; GitHub decisions retain rationale and rejected alternatives.

## Decision links

- [Disclosure-safe data contract](https://github.com/frankieramirez/comicarr/issues/600)
- [Generation and download contract](https://github.com/frankieramirez/comicarr/issues/601)
- [Settings interaction](https://github.com/frankieramirez/comicarr/issues/602)
- [Security and acceptance contract](https://github.com/frankieramirez/comicarr/issues/603)
- [Canonical specification and implementation shape](https://github.com/frankieramirez/comicarr/issues/605)
- [Exact v1 contract assets](https://github.com/frankieramirez/comicarr/issues/606)

## 1. Purpose, operator, threat model, terminology

The Support bundle is a downloadable archive of **allowlisted diagnostic facts**, engineered for public issue attachment **after mandatory operator review**. If anything appears sensitive, the operator shares it privately with maintainers instead.

**CarePackage** is the legacy implementation name only. It must not appear in user-facing copy once disclosure is activated.

Threat model: data minimization plus closed-schema validation and archive-wide canary tests. Operator judgment remains part of the disclosure boundary.

## 2. V1 archive and packaged assets

Archive members, in fixed order:

1. `README.txt` — static disclosure guidance (no runtime values)
2. `manifest.json` — contract metadata, source availability, integrity digests
3. `diagnostics.json` — allowlisted diagnostic projection

Packaged immutable assets (loaded via `importlib.resources`):

```text
comicarr/app/system/support_bundle_contract/v1/
├── README.txt
├── manifest.schema.json
├── diagnostics.schema.json
└── field-manifest.json
```

Field-level and byte-level content lives in those assets; this document does not duplicate them.

Response filename: `comicarr-support-bundle-v1.zip`  
Contract header: `X-Comicarr-Support-Bundle-Contract: 1`  
Status header: `X-Comicarr-Support-Bundle-Status: complete|partial`

## 3. HTTP, module, lifecycle, concurrency, bounds, failures

### HTTP

- `POST /api/system/support-bundle` only
- Session authentication via `require_session` (no API key / OPDS / unauthenticated)
- CSRF: `X-Requested-With: ComicarrFrontend`
- No request body or query options
- Success: `200 application/zip` with in-memory bytes (`Response`, not `FileResponse`)
- Caching: `Cache-Control: no-store, private`, `Pragma: no-cache`; no ETag or Last-Modified

### Module seam

`generate_support_bundle(ctx) -> SupportBundleArtifact`

Artifact fields: `content`, `contract_version`, `filename`, `status`.

Callers never see collectors, paths, rows, raw config, logs, writers, or validators.

### Lifecycle

1. Acquire process-wide non-blocking single-flight lock  
2. Capture one UTC generation time and runtime/config snapshot under the runtime lock  
3. Collect allowlisted projections (DB via one read connection shared with health)  
4. Normalize closed objects  
5. Validate before serialization  
6. Deterministic JSON + fixed ZIP assembly  
7. Re-open and validate final ZIP  
8. Return immutable bytes; release lock in `finally`

No persistence, staging directory, job record, polling, or cleanup task.

### Bounds

| Cap | Limit |
|---|---|
| `README.txt` | 16 KiB |
| Each JSON member | 256 KiB |
| Total uncompressed | 512 KiB |
| Final ZIP | 512 KiB |

No network or subprocess work. Fixed aggregate query set. No row export.

### Typed failures

| Code | HTTP | Retryable | Retry-After |
|---|---|---|---|
| `support_bundle_in_progress` | 409 | true | 2 |
| `support_bundle_unavailable` | 503 | true | — |
| `support_bundle_validation_failed` | 500 | false | — |
| `support_bundle_generation_failed` | 500 | true | — |

Exact `detail` strings are locked in #606. Optional source failure yields a valid **partial** bundle, not an HTTP error.

## 4. Source authority and complete/partial semantics

Sources resolve only from active `AppContext` and the active SQLAlchemy engine. Paths are internal inputs and never serialized. No guessed-default fallback.

| Source | Role |
|---|---|
| build | Mandatory |
| runtime | Mandatory |
| configuration | Mandatory |
| database | Optional |
| health | Optional |

`bundle_status` is `complete` iff both optional sources are available; otherwise `partial`. Cross-document invariants (product version match, digest/size match, optional object presence) are enforced after schema validation.

The modern module never imports or instantiates the legacy `carePackage` collector.

## 5. Settings placement and disclosure flow

Settings → About, between What's new and Build / environment:

1. **Create** — build a fresh archive  
2. **Inspect** — open the three files  
3. **Share** — public only when comfortable; otherwise private to a maintainer  

Group action: **Create support bundle**. Confirmation required on every generation. Full state matrix and accessibility requirements are in #602.

## 6. Disclosure guards and acceptance

Required automated gates include closed-schema and field-manifest parity, archive-wide canary scanning, single-flight lock release, live SQLite/PostgreSQL/MySQL projection equivalence, session/CSRF preservation, frontend state matrix, and authenticated browser smoke.

Public-attachment documentation (`SECURITY.md`, `CONTRIBUTING.md`, bug template) changes only in the disclosure-activation PR after maintainer/security review of seeded complete and partial artifacts.

Terminology guard: `scripts/support_bundle_legacy_terms_allowlist.txt`.

## 7. Versioning

One independent integer contract version. Once shipped, `v1/` is immutable. Any disclosure-shape change requires a reviewed `v2/` package and header/filename change. Product versions and Changesets do not alter the contract version automatically.

## 8. Implementation stack

1. Contract and backend  
2. Frontend interaction  
3. Disclosure activation  

Each PR is independently reviewable. The first two may merge while the feature remains undiscoverable in issue-reporting docs.

## 9. Traceability

| Section | Decision |
|---|---|
| Data exclusions, archive members, projection categories | #600 |
| HTTP, lifecycle, lock, typed failures, legacy boundary | #601 |
| Settings UI, states, accessibility, helper | #602 |
| Tests, canaries, dialect matrix, human review gate | #603 |
| Spec locations, packaging, PR stack | #605 |
| Exact bytes, schemas, enums, fixtures, error sentences | #606 |
