import { afterEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import RelativeTime from "@/components/ui/RelativeTime";

describe("RelativeTime", () => {
  afterEach(() => {
    vi.useRealTimers();
  });

  it("renders a relative value with the absolute time available", () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-07-10T09:00:00"));

    render(<RelativeTime value="2026-07-10 08:00:00" />);

    const time = screen.getByText("1 hour ago");
    expect(time.getAttribute("datetime")).toContain("2026-07-10T");
    expect(time.getAttribute("title")).toBeTruthy();
  });

  it("renders a fallback for invalid timestamps", () => {
    render(<RelativeTime value="not-a-date" />);

    expect(screen.getByText("—")).toBeTruthy();
  });
});
