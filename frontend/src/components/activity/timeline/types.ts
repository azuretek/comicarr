/**
 * Activity Center timeline types.
 *
 * Field contract mirrors activity_events / band DTOs (Activity Center ADR).
 * Severity is a pure function of status — never stored.
 */

export type Activity =
  "search" | "grab" | "download" | "import" | "refresh" | "add" | "tag";

/** `retrying` is deliberately absent — #432. */
export type EventStatus =
  | "started"
  | "succeeded"
  | "no_match"
  | "cancelled"
  | "failed"
  | "blocked"
  | "needs_attention";

export type SubjectType = "issue" | "annual" | "series" | "arc" | "run";

export type Severity = "normal" | "action_required";

/** Severity is a pure function of status (#426) — never stored. */
export function severityOf(status: string): Severity {
  return status === "failed" ||
    status === "blocked" ||
    status === "needs_attention"
    ? "action_required"
    : "normal";
}

/** Optional run counts when producers embed them (not a DB column today). */
export interface RunCounts {
  accepted: number;
  grabbed: number;
  no_match: number;
  failed: number;
  /** Present only while the run is open — determinate per-run progress. */
  resolved?: number;
}

export interface TimelineEvent {
  event_id: number | string;
  created_at: string;
  activity: Activity | string;
  status: EventStatus | string;
  subject_type: SubjectType | string;
  subject_id: string;
  /** Denormalized — the timeline must survive deletion of its subject. */
  subject_label: string;
  reason_code?: string | null;
  reason_detail?: string | null;
  provider?: string | null;
  run_id?: string | null;
  release_key?: string | null;
  parent_series_id?: string | null;
  scope_type?: string | null;
  scope_id?: string | null;
  /** Not on the table; optional future/envelope field for run brackets. */
  counts?: RunCounts | null;
}

/**
 * Needs-attention band row from pipeline_journal (derived ledger, not narrative).
 * Field names match the journal row shape from GET /api/activity/band.
 */
export interface BandItem {
  release_key: string;
  stage: "failed" | "manual_review" | string;
  issueid?: string | null;
  provider?: string | null;
  nzbname?: string | null;
  fail_reason?: string | null;
  updated_date: string;
  status?: string | null;
  /** Optional display helpers when present on an enriched DTO. */
  subject_label?: string | null;
}

/**
 * One subject's story (#428). Identity is `(subject_type, subject_id)`.
 * Opened by an advance, closed by a terminal allowlist pair. Always collapsed.
 */
export interface Story {
  key: string;
  subject_type: string;
  subject_id: string;
  subject_label: string;
  parent_series_id?: string | null;
  /** Opening event's created_at — position, and it never re-sorts. */
  opened_at: string;
  events: TimelineEvent[];
  /** Null while open; the closing event once closed. */
  closer: TimelineEvent | null;
}

export type FeedNode = Story;

export interface TimelinePage {
  results: TimelineEvent[];
  total: number;
  limit: number;
  offset: number;
  has_more: boolean;
}

export interface BandPage {
  results: BandItem[];
  total: number;
}
