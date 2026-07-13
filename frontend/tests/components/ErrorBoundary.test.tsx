import { describe, expect, it, vi } from "vitest";
import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { renderMinimal } from "../test-utils";
import ErrorBoundary from "@/components/ErrorBoundary";

function ThrowError(): never {
  throw new Error("Unable to render issue shelf");
}

describe("ErrorBoundary", () => {
  it("shows a clear recovery state when a child component fails", () => {
    vi.spyOn(console, "error").mockImplementation(() => undefined);

    renderMinimal(
      <ErrorBoundary>
        <ThrowError />
      </ErrorBoundary>,
    );

    expect(
      screen.getByRole("heading", { name: "This screen needs a fresh start." }),
    ).toBeTruthy();
    expect(screen.getByText("App error")).toBeTruthy();
    expect(
      screen.getByRole("button", { name: "Reload Comicarr" }),
    ).toBeTruthy();
    expect(
      screen.getByText(/does not change your library or settings/i),
    ).toBeTruthy();
  });

  it("reloads the application from the recovery action", async () => {
    vi.spyOn(console, "error").mockImplementation(() => undefined);
    const reload = vi.spyOn(window.location, "reload");
    const user = userEvent.setup();

    renderMinimal(
      <ErrorBoundary>
        <ThrowError />
      </ErrorBoundary>,
    );

    await user.click(screen.getByRole("button", { name: "Reload Comicarr" }));

    expect(reload).toHaveBeenCalledOnce();
  });
});
