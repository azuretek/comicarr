/**
 * GET /api/system/version — update availability is Changesets semver
 * (`update_state`), not commit lag. Local display chrome still uses
 * `formatAppVersion` / APP_VERSION, not these fields, for the chip text.
 */

export type UpdateState = "behind" | "current" | "unknown";

export type UpdateReason =
  "never_checked" | "unreachable" | "rate_limited" | string;

export type InstallType = "docker" | "git" | "source" | "win" | string;

export interface SystemVersionInfo {
  current_version?: string | null;
  current_version_name?: string | null;
  current_release_name?: string | null;
  latest_version?: string | null;
  release_version?: string | null;
  update_state?: UpdateState | string | null;
  update_reason?: UpdateReason | null;
  install_type?: InstallType | null;
  current_branch?: string | null;
  build?: {
    id?: string | null;
    commit?: string | null;
    release?: string | null;
    version?: string | null;
    source?: string | null;
    verified?: boolean;
  };
}

export interface ReleaseNotesSection {
  version: string;
  bullets: string[];
}

export interface ReleaseNotesResponse {
  sections: ReleaseNotesSection[];
}
