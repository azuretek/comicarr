/**
 * Install-type how-to-update copy for the update-available popover (#473 / #452).
 * Instructions only — Comicarr never mutates the install from this surface.
 */

import type { InstallType } from "@/types/version";

export const GHCR_IMAGE = "ghcr.io/frankieramirez/comicarr";

export function releaseTagUrl(latestVersion: string): string {
  const tag = latestVersion.startsWith("v")
    ? latestVersion
    : `v${latestVersion}`;
  return `https://github.com/frankieramirez/comicarr/releases/tag/${tag}`;
}

export function pinImageTag(latestVersion: string): string {
  const tag = latestVersion.startsWith("v")
    ? latestVersion
    : `v${latestVersion}`;
  return `${GHCR_IMAGE}:${tag}`;
}

export interface UpdateGuidance {
  title: string;
  intro: string;
  /** Copyable shell blocks; empty for prose-only types (win/source). */
  commands: string[];
  note?: string;
}

export function getUpdateGuidance(
  installType: InstallType | null | undefined,
  latestVersion: string,
): UpdateGuidance {
  const tag = latestVersion.startsWith("v")
    ? latestVersion
    : `v${latestVersion}`;
  const pinned = pinImageTag(latestVersion);
  const kind = (installType || "source").toLowerCase();

  if (kind === "docker") {
    return {
      title: "How to update (Docker)",
      intro:
        "Pull the notified release and recreate the container on the host. Comicarr cannot replace its own container.",
      commands: [
        ["docker compose pull", "docker compose up -d"].join("\n"),
        `docker pull ${pinned}`,
      ],
      note: "Prefer Compose when you use a compose file. The plain pull pins the image to this release — not floating :latest.",
    };
  }

  if (kind === "git") {
    return {
      title: "How to update (git)",
      intro: `Check out the release tag ${tag}, then restart Comicarr. Do not git pull a branch — branches are not the release line.`,
      commands: [["git fetch --tags origin", `git checkout ${tag}`].join("\n")],
      note: "Restart the Comicarr process after checkout.",
    };
  }

  if (kind === "win") {
    return {
      title: "How to update (Windows)",
      intro:
        "Self-update is not supported for this install. Download the notified release from GitHub and upgrade using your usual install path.",
      commands: [],
      note: "Use the Release link for the exact tag notes and assets.",
    };
  }

  // source and anything unknown
  return {
    title: "How to update (source)",
    intro: `Upgrade this source install to ${tag} from the GitHub release (reinstall or replace the tree from that tag). Do not run in-app tarball overwrite commands.`,
    commands: [],
    note: "See the Release page for that version’s notes and packaging.",
  };
}
