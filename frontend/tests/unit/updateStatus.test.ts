import { describe, expect, it } from "vitest";
import {
  formatUnknownUpdateReason,
  formatUpdateDiagnostic,
} from "@/lib/updateStatus";

describe("formatUnknownUpdateReason", () => {
  it("maps never_checked to operator language", () => {
    expect(formatUnknownUpdateReason("never_checked")).toBe("Not checked yet");
  });

  it("maps unreachable to operator language", () => {
    expect(formatUnknownUpdateReason("unreachable")).toBe(
      "Could not reach the release source",
    );
  });

  it("maps rate_limited to operator language", () => {
    expect(formatUnknownUpdateReason("rate_limited")).toBe(
      "Rate limited — will retry on the normal schedule",
    );
  });

  it("defaults missing reason to not checked yet", () => {
    expect(formatUnknownUpdateReason(null)).toBe("Not checked yet");
    expect(formatUnknownUpdateReason(undefined)).toBe("Not checked yet");
  });
});

describe("formatUpdateDiagnostic", () => {
  it("shows current → latest when behind", () => {
    expect(
      formatUpdateDiagnostic({
        update_state: "behind",
        release_version: "0.21.0",
        latest_version: "0.22.0",
      }),
    ).toBe("Update available: 0.21.0 → 0.22.0");
  });

  it("shows up to date when current", () => {
    expect(
      formatUpdateDiagnostic({
        update_state: "current",
        release_version: "0.22.0",
        latest_version: "0.22.0",
      }),
    ).toBe("Up to date");
  });

  it("shows unknown reason in operator language", () => {
    expect(
      formatUpdateDiagnostic({
        update_state: "unknown",
        update_reason: "rate_limited",
      }),
    ).toBe("Rate limited — will retry on the normal schedule");
  });
});
