import { describe, expect, it, vi } from "vitest";
import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { renderMinimal } from "../test-utils";
import { RouteLoader } from "@/components/RouteLoader";

describe("RouteLoader", () => {
  it("shows a visible loading state until a route module resolves", async () => {
    let resolveModule:
      ((module: { default: React.ComponentType }) => void) | undefined;
    const load = vi.fn(
      () =>
        new Promise<{ default: React.ComponentType }>((resolve) => {
          resolveModule = resolve;
        }),
    );

    renderMinimal(<RouteLoader load={load} />);

    expect(screen.getByRole("status").textContent).toContain("Loading page");

    resolveModule?.({ default: () => <h1>Wanted</h1> });

    expect(await screen.findByRole("heading", { name: "Wanted" })).toBeTruthy();
  });

  it("retries a rejected route import without requiring a full reload", async () => {
    const load = vi
      .fn<() => Promise<{ default: React.ComponentType }>>()
      .mockRejectedValueOnce(new Error("missing chunk"))
      .mockResolvedValueOnce({ default: () => <h1>Wanted</h1> });
    const user = userEvent.setup();

    renderMinimal(<RouteLoader load={load} />);

    expect((await screen.findByRole("alert")).textContent).toContain(
      "Unable to load this page",
    );
    await user.click(screen.getByRole("button", { name: "Try again" }));

    expect(await screen.findByRole("heading", { name: "Wanted" })).toBeTruthy();
    expect(load).toHaveBeenCalledTimes(2);
  });
});
