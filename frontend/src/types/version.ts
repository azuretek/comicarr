/**
 * Release-notes API types. Version/update state lives in
 * ``@/lib/updateStatus`` (shared with Settings → About).
 */

export type InstallType = "docker" | "git" | "source" | "win" | string;

export interface ReleaseNotesSection {
  version: string;
  bullets: string[];
}

export interface ReleaseNotesResponse {
  sections: ReleaseNotesSection[];
}

/** Settings → About archive (server floors/pads depth). */
export interface WhatsNewArchiveResponse {
  sections: ReleaseNotesSection[];
  pending: { from: string; to: string } | null;
  current: string | null;
  last_seen: string | null;
}

export interface WhatsNewDismissResponse {
  success: boolean;
  last_seen_version?: string;
  error?: string;
}
