import { describe, expect, it } from "vitest";
import {
  formatWantedAcquisitionAnnotation,
  WANTED_ANNOTATION_NEVER_SEARCHED,
  WANTED_ANNOTATION_SEARCHING,
} from "@/lib/wantedAnnotation";

describe("formatWantedAcquisitionAnnotation", () => {
  it("labels missing annotations as never searched", () => {
    expect(formatWantedAcquisitionAnnotation(null)).toBe(
      WANTED_ANNOTATION_NEVER_SEARCHED,
    );
    expect(formatWantedAcquisitionAnnotation(undefined)).toBe(
      WANTED_ANNOTATION_NEVER_SEARCHED,
    );
    expect(
      formatWantedAcquisitionAnnotation({ state: null, attempt_count: 0 }),
    ).toBe(WANTED_ANNOTATION_NEVER_SEARCHED);
  });

  it("labels accepted and running as searching… without inventing progress", () => {
    expect(
      formatWantedAcquisitionAnnotation({
        state: "accepted",
        attempt_count: 0,
      }),
    ).toBe(WANTED_ANNOTATION_SEARCHING);
    expect(
      formatWantedAcquisitionAnnotation({
        state: "running",
        attempt_count: 2,
      }),
    ).toBe(WANTED_ANNOTATION_SEARCHING);
    // attempt_count > 0 with accepted is retry-pending (#432) — still searching…
    expect(
      formatWantedAcquisitionAnnotation({
        state: "accepted",
        attempt_count: 3,
      }),
    ).toBe(WANTED_ANNOTATION_SEARCHING);
  });

  it("labels no_match with sticky try counts and no countdown", () => {
    expect(
      formatWantedAcquisitionAnnotation({
        state: "no_match",
        attempt_count: 3,
      }),
    ).toBe("no match · 3 tries");
    expect(
      formatWantedAcquisitionAnnotation({
        state: "no_match",
        attempt_count: 1,
      }),
    ).toBe("no match · 1 try");
  });

  it("does not fabricate next_attempt_at countdowns for any state", () => {
    const labels = [
      formatWantedAcquisitionAnnotation({
        state: "accepted",
        attempt_count: 4,
      }),
      formatWantedAcquisitionAnnotation({
        state: "no_match",
        attempt_count: 4,
      }),
      formatWantedAcquisitionAnnotation({
        state: "failed",
        attempt_count: 4,
      }),
    ];
    for (const label of labels) {
      expect(label).not.toMatch(/retry/i);
      expect(label).not.toMatch(/%/);
      expect(label).not.toMatch(/\d+h|\d+m|\d+s/);
    }
  });

  it("keeps other terminal states countdown-free and operator-readable", () => {
    expect(
      formatWantedAcquisitionAnnotation({
        state: "failed",
        attempt_count: 2,
      }),
    ).toBe("failed · 2 tries");
    expect(
      formatWantedAcquisitionAnnotation({
        state: "blocked",
        attempt_count: 0,
      }),
    ).toBe("blocked");
    expect(
      formatWantedAcquisitionAnnotation({
        state: "cancelled",
        attempt_count: 1,
      }),
    ).toBe("cancelled");
    // succeeded is terminal — never claim searching while still on Wanted
    expect(
      formatWantedAcquisitionAnnotation({
        state: "succeeded",
        attempt_count: 1,
      }),
    ).toBe("matched");
  });
});
