import { version } from "../../package.json";

/**
 * Authoritative app release version for every user-facing UI surface
 * (sidebar, login, onboarding, Settings header, About).
 *
 * Sourced from frontend/package.json. Changesets + scripts/release/sync-version
 * keep this in lockstep with root package.json and pyproject.toml. Do not
 * substitute backend current_version / config.version here — those can be a
 * git SHA or stale install metadata and caused conflicting badges (#412).
 */
export const APP_VERSION: string = version;

/** Format for badges, e.g. `v0.18.5`. */
export function formatAppVersion(withPrefix = true): string {
  return withPrefix ? `v${APP_VERSION}` : APP_VERSION;
}
