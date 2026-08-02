/**
 * PROTOTYPE — throwaway mock for needs-attention band / triage (#526).
 * Shaped like production after actionability + grouping decisions.
 * Do not import from production paths.
 */

export type Stage = "failed" | "manual_review";

export type MockMember = {
  release_key: string;
  issue_label: string;
  updated_at: string;
  stage: Stage;
};

export type MockGroup = {
  group_key: string;
  comicid: string;
  series_label: string;
  base_reason: string;
  reason_phrase: string;
  member_count: number;
  newest_updated_at: string;
  oldest_updated_at: string;
  available_actions: string[];
  members: MockMember[];
};

/** Operator-facing phrases for admitted base tokens (draft for #526). */
export const REASON_PHRASES: Record<string, string> = {
  downloaded_invalid_artifact_command: "downloaded file failed post-process checks",
  invalid_recovered_postprocess_command: "recovered download has a bad post-process command",
  postprocess_error: "post-processing failed",
  invalid_postprocess_command: "post-process command is invalid",
  recovered_postprocess_error: "recovered download failed post-processing",
  ddl_artifact_state_persistence_error: "could not save download state (DDL)",
  torrent_artifact_state_persistence_error: "could not save download state (torrent)",
  nzb_artifact_state_persistence_error: "could not save download state (NZB)",
  reserved_without_persisted_acceptance: "download reserved but not fully accepted",
  route_acceptance_missing_identity: "acceptance missing identity fields",
  submission_outcome_unknown: "submission result unknown — check the downloader",
  route_not_restart_safe: "route is not safe to resume after restart",
  download_failed_no_auto_handling: "download failed — auto-handling is off",
  submission_rejected: "submission was rejected",
};

function members(
  series: string,
  n: number,
  stage: Stage,
  prefix: string,
  newest: string,
): MockMember[] {
  return Array.from({ length: n }, (_, i) => ({
    release_key: `${prefix}|${i + 1}`,
    issue_label: `${series} #${i + 1}`,
    updated_at: newest,
    stage,
  }));
}

function group(
  comicid: string,
  series: string,
  base_reason: string,
  n: number,
  stage: Stage,
  newest: string,
  oldest: string,
): MockGroup {
  const actions =
    stage === "failed"
      ? ["retry", "stop_wanting"]
      : ["import", "search_again", "stop_wanting"];
  return {
    group_key: `${comicid}|${base_reason}`,
    comicid,
    series_label: series,
    base_reason,
    reason_phrase: REASON_PHRASES[base_reason] ?? "something went wrong",
    member_count: n,
    newest_updated_at: newest,
    oldest_updated_at: oldest,
    available_actions: actions,
    members: members(series, Math.min(n, 8), stage, `${comicid}-${base_reason}`, newest),
  };
}

/** ~20 groups, production-ish weights after admission. */
export const MOCK_GROUPS: MockGroup[] = [
  group(
    "18839",
    "Looney Tunes",
    "downloaded_invalid_artifact_command",
    47,
    "manual_review",
    "2026-07-11T11:30:04Z",
    "2026-07-11T11:30:00Z",
  ),
  group(
    "158418",
    "X-Men: From the Ashes Infinity Comic",
    "downloaded_invalid_artifact_command",
    19,
    "manual_review",
    "2026-07-11T11:30:03Z",
    "2026-07-11T11:30:00Z",
  ),
  group(
    "91078",
    "Action Comics",
    "downloaded_invalid_artifact_command",
    15,
    "manual_review",
    "2026-07-11T11:30:02Z",
    "2026-07-11T11:30:00Z",
  ),
  group(
    "142577",
    "The Amazing Spider-Man",
    "postprocess_error",
    12,
    "manual_review",
    "2026-07-11T11:30:01Z",
    "2026-07-11T11:30:00Z",
  ),
  group(
    "148476",
    "Superman",
    "downloaded_invalid_artifact_command",
    11,
    "manual_review",
    "2026-07-11T11:30:01Z",
    "2026-07-11T11:30:00Z",
  ),
  group(
    "58231",
    "Swamp Thing",
    "invalid_recovered_postprocess_command",
    11,
    "manual_review",
    "2026-07-11T11:30:00Z",
    "2026-07-11T11:30:00Z",
  ),
  group(
    "145912",
    "Fantastic Four",
    "downloaded_invalid_artifact_command",
    10,
    "manual_review",
    "2026-07-11T11:30:00Z",
    "2026-07-11T11:30:00Z",
  ),
  group(
    "153968",
    "Transformers",
    "submission_outcome_unknown",
    10,
    "manual_review",
    "2026-07-10T08:00:00Z",
    "2026-07-09T12:00:00Z",
  ),
  group(
    "141907",
    "Batman/Superman: World's Finest",
    "download_failed_no_auto_handling",
    7,
    "failed",
    "2026-07-08T16:00:00Z",
    "2026-07-01T10:00:00Z",
  ),
  group(
    "120001",
    "Detective Comics",
    "submission_rejected",
    6,
    "failed",
    "2026-07-07T14:00:00Z",
    "2026-07-07T14:00:00Z",
  ),
  group(
    "120002",
    "Green Lantern",
    "downloaded_invalid_artifact_command",
    5,
    "manual_review",
    "2026-07-06T09:00:00Z",
    "2026-07-06T09:00:00Z",
  ),
  group(
    "120003",
    "Wonder Woman",
    "route_not_restart_safe",
    4,
    "manual_review",
    "2026-07-05T11:00:00Z",
    "2026-07-05T11:00:00Z",
  ),
  group(
    "120004",
    "Aquaman",
    "postprocess_error",
    4,
    "manual_review",
    "2026-07-04T11:00:00Z",
    "2026-07-04T11:00:00Z",
  ),
  group(
    "120005",
    "Flash",
    "downloaded_invalid_artifact_command",
    3,
    "manual_review",
    "2026-07-03T11:00:00Z",
    "2026-07-03T11:00:00Z",
  ),
  group(
    "120006",
    "Hawkman",
    "reserved_without_persisted_acceptance",
    3,
    "manual_review",
    "2026-07-02T11:00:00Z",
    "2026-07-02T11:00:00Z",
  ),
  group(
    "120007",
    "Martian Manhunter",
    "downloaded_invalid_artifact_command",
    2,
    "manual_review",
    "2026-07-01T11:00:00Z",
    "2026-07-01T11:00:00Z",
  ),
  group(
    "120008",
    "Shazam!",
    "ddl_artifact_state_persistence_error",
    2,
    "manual_review",
    "2026-06-30T11:00:00Z",
    "2026-06-30T11:00:00Z",
  ),
  group(
    "orphan-rk-1",
    "Series (unlabelled)",
    "downloaded_invalid_artifact_command",
    1,
    "manual_review",
    "2026-06-29T11:00:00Z",
    "2026-06-29T11:00:00Z",
  ),
  group(
    "120009",
    "Booster Gold",
    "route_acceptance_missing_identity",
    1,
    "manual_review",
    "2026-06-28T11:00:00Z",
    "2026-06-28T11:00:00Z",
  ),
  group(
    "120010",
    "Blue Beetle",
    "submission_rejected",
    1,
    "failed",
    "2026-06-27T11:00:00Z",
    "2026-06-27T11:00:00Z",
  ),
];

export const TOTAL_GROUPS = MOCK_GROUPS.length;
export const TOTAL_MEMBERS = MOCK_GROUPS.reduce((s, g) => s + g.member_count, 0);

export function rankByVolumeThenNewest(groups: MockGroup[]): MockGroup[] {
  return [...groups].sort((a, b) => {
    if (b.member_count !== a.member_count) return b.member_count - a.member_count;
    return b.newest_updated_at.localeCompare(a.newest_updated_at);
  });
}

export function rankByNewest(groups: MockGroup[]): MockGroup[] {
  return [...groups].sort((a, b) => b.newest_updated_at.localeCompare(a.newest_updated_at));
}

export function actionLabel(id: string): string {
  switch (id) {
    case "retry":
      return "Retry";
    case "search_again":
      return "Search again";
    case "import":
      return "Import";
    case "stop_wanting":
      return "Stop wanting";
    default:
      return id;
  }
}
