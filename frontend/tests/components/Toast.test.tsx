import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ToastProvider, useToast } from "@/components/ui/toast";

function ErrorToastTrigger() {
  const { addToast } = useToast();
  return (
    <button
      type="button"
      onClick={() => addToast({ type: "error", message: "Logout failed" })}
    >
      Show error
    </button>
  );
}

describe("Toast accessibility", () => {
  it("announces error feedback and labels its dismiss control", async () => {
    render(
      <ToastProvider>
        <ErrorToastTrigger />
      </ToastProvider>,
    );

    fireEvent.click(screen.getByRole("button", { name: "Show error" }));

    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toContain("Logout failed");
    expect(
      screen.getByRole("button", { name: "Dismiss notification" }),
    ).toBeTruthy();
  });
});
