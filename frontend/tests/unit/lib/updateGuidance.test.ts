import { describe, expect, it } from "vitest";
import {
  getUpdateGuidance,
  pinImageTag,
  releaseTagUrl,
} from "@/lib/updateGuidance";

describe("updateGuidance", () => {
  it("builds release tag URL with v prefix", () => {
    expect(releaseTagUrl("0.21.0")).toBe(
      "https://github.com/frankieramirez/comicarr/releases/tag/v0.21.0",
    );
    expect(releaseTagUrl("v0.21.0")).toBe(
      "https://github.com/frankieramirez/comicarr/releases/tag/v0.21.0",
    );
  });

  it("pins docker image to notified release not :latest", () => {
    expect(pinImageTag("0.21.0")).toBe("ghcr.io/frankieramirez/comicarr:0.21.0");
    const g = getUpdateGuidance("docker", "0.21.0");
    expect(g.commands.some((c) => c.includes(":0.21.0"))).toBe(true);
    expect(g.commands.some((c) => c.includes(":latest"))).toBe(false);
    expect(g.commands[0]).toContain("docker compose pull");
  });

  it("strips the v prefix the release line carries — registry tags are bare semver", () => {
    // release.yml pushes ghcr.io/frankieramirez/comicarr:${version}, where
    // version is package.json's bare semver. A :v-prefixed pull 404s.
    expect(pinImageTag("v0.21.0")).toBe(
      "ghcr.io/frankieramirez/comicarr:0.21.0",
    );
    const g = getUpdateGuidance("docker", "v0.21.0");
    expect(g.commands.some((c) => c.includes(":v0.21.0"))).toBe(false);
    expect(g.commands.some((c) => c.includes(":0.21.0"))).toBe(true);
  });

  it("does not claim a bare pull pins a compose stack", () => {
    // docker-compose.yml ships `image: ...:latest`; a pinned `docker pull`
    // only warms the local cache, so the recreate still resolves :latest.
    const g = getUpdateGuidance("docker", "0.21.0");
    expect(g.note).not.toMatch(/plain pull pins/i);
    expect(g.note).toMatch(/image:/);
  });

  it("git guidance checks out tag not branch pull", () => {
    const g = getUpdateGuidance("git", "0.21.0");
    const blob = g.commands.join("\n");
    expect(blob).toContain("git checkout v0.21.0");
    expect(blob).not.toMatch(/git pull/i);
  });

  it("win is unsupported prose without pretend commands", () => {
    const g = getUpdateGuidance("win", "0.21.0");
    expect(g.commands).toEqual([]);
    expect(g.intro.toLowerCase()).toMatch(/not supported/);
  });

  it("source is reinstall guidance without apply commands", () => {
    const g = getUpdateGuidance("source", "0.21.0");
    expect(g.commands).toEqual([]);
    expect(g.intro.toLowerCase()).toMatch(/reinstall|upgrade/);
  });
});
