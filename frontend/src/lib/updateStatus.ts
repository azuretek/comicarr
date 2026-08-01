/**
 * Operator-facing copy for update diagnostics (Settings → About → Updates).
 * Codes match GET /api/system/version update_reason when update_state is unknown.
 */

export type UpdateState = "behind" | "current" | "unknown" | string;
export type UpdateReason =
  "never_checked" | "unreachable" | "rate_limited" | string | null | undefined;

const UNKNOWN_REASON_COPY: Record<string, string> = {
  never_checked: "Not checked yet",
  unreachable: "Could not reach the release source",
  rate_limited: "Rate limited — will retry on the normal schedule",
};

export function formatUnknownUpdateReason(reason: UpdateReason): string {
  if (!reason) return UNKNOWN_REASON_COPY.never_checked;
  return UNKNOWN_REASON_COPY[reason] ?? "Update status is unavailable";
}

/** Open-closed pending range ends for post-upgrade What's New (#474). */
export interface PendingWhatsNew {
  /** Exclusive lower bound (LAST_SEEN_VERSION). */
  from: string;
  /** Inclusive upper bound (current release). */
  to: string;
}

export interface VersionInfo {
  current_version?: string | null;
  latest_version?: string | null;
  release_version?: string | null;
  update_state?: UpdateState | null;
  update_reason?: UpdateReason;
  install_type?: string | null;
  message?: string | null;
  /** When set, show the post-upgrade modal / unread archive state. */
  pending_whats_new?: PendingWhatsNew | null;
}

/** One-line diagnostic for the Updates group (not a second badge). */
export function formatUpdateDiagnostic(info: VersionInfo | undefined): string {
  if (!info) return "Loading update status…";

  const state = info.update_state ?? "unknown";
  if (state === "behind") {
    const current = info.release_version || "—";
    const latest = info.latest_version || "—";
    return `Update available: ${current} → ${latest}`;
  }
  if (state === "current") {
    return "Up to date";
  }
  return formatUnknownUpdateReason(info.update_reason);
}
