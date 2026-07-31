import { describe, it, expect } from "vitest";
import packageJson from "../../../package.json";
import rootPackageJson from "../../../../package.json";
import { APP_VERSION, formatAppVersion } from "@/lib/version";

describe("version", () => {
  it("matches frontend package.json", () => {
    expect(APP_VERSION).toBe(packageJson.version);
    expect(APP_VERSION).toMatch(/^\d+\.\d+\.\d+/);
  });

  it("stays in lockstep with the root package release version", () => {
    // Changesets + scripts/release/sync-version.mjs keep these aligned.
    // Divergence here is the same class of bug as #412.
    expect(APP_VERSION).toBe(rootPackageJson.version);
  });

  it("formats with and without v prefix", () => {
    expect(formatAppVersion()).toBe(`v${packageJson.version}`);
    expect(formatAppVersion(true)).toBe(`v${packageJson.version}`);
    expect(formatAppVersion(false)).toBe(packageJson.version);
  });
});
