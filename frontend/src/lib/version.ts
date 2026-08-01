import { version } from "../../package.json";

/**
 * Authoritative app release version for every user-facing UI surface.
 *
 * Consumers (must import only from this module):
 * - VersionChip (sidebar header pill)
 * - LoginPage badge
 * - OnboardingDialog welcome label
 * - SettingsPage header + AboutTab
 *
 * Sourced from frontend/package.json. Changesets + scripts/release/sync-version
 * keep this in lockstep with root package.json and pyproject.toml (backend
 * get_release_version / config.version). Do not substitute backend
 * current_version or config.version in UI chrome — those can be a git SHA or
 * stale install metadata and caused conflicting badges (#412).
 */
export const APP_VERSION: string = version;

/** Format for badges. Prefer this helper over raw APP_VERSION in UI. */
export function formatAppVersion(withPrefix = true): string {
  return withPrefix ? `v${APP_VERSION}` : APP_VERSION;
}
