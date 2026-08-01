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
