import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

/**
 * Issue #470: retire both ends of the dead check_update toast path.
 * The consumer must not register a check_update listener or toast "N commits behind".
 */
describe("useServerEvents dead update toast path", () => {
  const source = readFileSync(
    resolve(__dirname, "../../src/hooks/useServerEvents.ts"),
    "utf8",
  );
  const events = readFileSync(
    resolve(__dirname, "../../src/types/events.ts"),
    "utf8",
  );

  it("does not listen for check_update SSE events", () => {
    expect(source).not.toMatch(/check_update/);
    expect(source).not.toMatch(/CheckUpdateEventData/);
    expect(source).not.toMatch(/commits_behind/);
    expect(source).not.toMatch(/commits behind/i);
  });

  it("does not export CheckUpdateEventData", () => {
    expect(events).not.toMatch(/CheckUpdateEventData/);
    expect(events).not.toMatch(/check_update/);
    expect(events).not.toMatch(/commits_behind/);
  });
});
