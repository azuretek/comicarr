import { describe, expect, it } from "vitest";
import { isUpdateBehind } from "@/hooks/useVersion";

describe("isUpdateBehind", () => {
  it("is true only on successful poll with update_state behind", () => {
    expect(
      isUpdateBehind("success", {
        update_state: "behind",
        latest_version: "0.21.0",
      }),
    ).toBe(true);
  });

  it("treats current and unknown as no cue", () => {
    expect(
      isUpdateBehind("success", {
        update_state: "current",
        latest_version: "0.20.0",
      }),
    ).toBe(false);
    expect(
      isUpdateBehind("success", {
        update_state: "unknown",
        update_reason: "never_checked",
        latest_version: null,
      }),
    ).toBe(false);
  });

  it("does not sticky-show behind on transport error", () => {
    expect(
      isUpdateBehind("error", {
        update_state: "behind",
        latest_version: "0.21.0",
      }),
    ).toBe(false);
    expect(isUpdateBehind("pending", undefined)).toBe(false);
  });

  it("requires latest_version when behind", () => {
    expect(
      isUpdateBehind("success", {
        update_state: "behind",
        latest_version: null,
      }),
    ).toBe(false);
  });
});
