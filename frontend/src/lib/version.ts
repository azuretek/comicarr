import { version } from "../../package.json";

/**
 * App release version for UI chrome (sidebar, login, onboarding).
 *
 * Sourced from frontend/package.json. Changesets keeps this in sync with the
 * root package and pyproject versions on release.
 */
export const APP_VERSION: string = version;

/** Format for badges, e.g. `v0.18.5`. */
export function formatAppVersion(withPrefix = true): string {
  return withPrefix ? `v${APP_VERSION}` : APP_VERSION;
}
