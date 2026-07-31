import { describe, expect, it } from "vitest";
import {
  displayComicDate,
  isUnknownComicDate,
  pickComicDate,
  UNKNOWN_DATE_DISPLAY,
} from "@/lib/format";

describe("isUnknownComicDate", () => {
  it("treats null, undefined, empty, and sentinel as unknown", () => {
    expect(isUnknownComicDate(null)).toBe(true);
    expect(isUnknownComicDate(undefined)).toBe(true);
    expect(isUnknownComicDate("")).toBe(true);
    expect(isUnknownComicDate("   ")).toBe(true);
    expect(isUnknownComicDate("0000-00-00")).toBe(true);
  });

  it("treats valid ISO dates as known", () => {
    expect(isUnknownComicDate("2025-08-01")).toBe(false);
    expect(isUnknownComicDate("1999-01-15")).toBe(false);
  });
});

describe("pickComicDate", () => {
  it("skips sentinel and empty candidates in favor of a valid date", () => {
    expect(pickComicDate("0000-00-00", null, "", "2024-03-12")).toBe(
      "2024-03-12",
    );
  });

  it("prefers the first valid candidate (release before issue)", () => {
    expect(pickComicDate("2024-01-10", "2024-02-20")).toBe("2024-01-10");
  });

  it("returns null when every candidate is unknown", () => {
    expect(pickComicDate("0000-00-00", null, "", undefined)).toBeNull();
  });
});

describe("displayComicDate", () => {
  it("renders sentinel, null, and empty as the placeholder", () => {
    expect(displayComicDate("0000-00-00")).toBe(UNKNOWN_DATE_DISPLAY);
    expect(displayComicDate(null)).toBe(UNKNOWN_DATE_DISPLAY);
    expect(displayComicDate("")).toBe(UNKNOWN_DATE_DISPLAY);
    expect(displayComicDate(undefined)).toBe(UNKNOWN_DATE_DISPLAY);
  });

  it("passes valid ISO dates through unchanged", () => {
    expect(displayComicDate("2025-08-01")).toBe("2025-08-01");
  });

  it("allows a custom placeholder", () => {
    expect(displayComicDate("0000-00-00", "Unknown")).toBe("Unknown");
  });
});
