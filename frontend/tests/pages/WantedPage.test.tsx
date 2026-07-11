import { describe, expect, it, vi } from "vitest";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { server } from "../mocks/server";
import { render, screen } from "../test-utils";
import WantedPage from "@/pages/WantedPage";

const wantedResponse = {
  issues: [],
  pagination: { total: 0, limit: 50, offset: 0, has_more: false },
};

function renderWantedWithForceResult(result: Record<string, unknown>) {
  server.use(
    http.get("/api/wanted", () => HttpResponse.json(wantedResponse)),
    http.post("/api/search/force", () => HttpResponse.json(result)),
  );
  vi.stubGlobal(
    "confirm",
    vi.fn(() => true),
  );
  return render(<WantedPage />);
}

describe("WantedPage", () => {
  it("reports an accepted force search with its accepted issue count", async () => {
    const user = userEvent.setup();
    renderWantedWithForceResult({
      success: true,
      status: "accepted",
      run_id: "run-123",
      accepted: 3,
      message: "Search initiated for wanted issues",
    });

    await user.click(
      await screen.findByRole("button", { name: /force search/i }),
    );

    expect(
      await screen.findByText(
        "Search accepted — 3 wanted issues queued. Run run-123.",
      ),
    ).toBeTruthy();
  });

  it("reports a completed no-match search without presenting it as a failure", async () => {
    const user = userEvent.setup();
    renderWantedWithForceResult({
      success: true,
      status: "no_match",
      run_id: "run-no-match",
      accepted: 0,
      message: "No eligible wanted issues found",
    });

    await user.click(
      await screen.findByRole("button", { name: /force search/i }),
    );

    expect(
      await screen.findByText(
        "No eligible wanted issues found. Run run-no-match.",
      ),
    ).toBeTruthy();
    expect(screen.getByText("Nothing to search")).toBeTruthy();
    expect(
      screen.queryByText(
        "Search accepted — 0 wanted issues queued. Run run-no-match.",
      ),
    ).toBeNull();
  });

  it("reports a blocked force search without a success toast", async () => {
    const user = userEvent.setup();
    renderWantedWithForceResult({
      success: false,
      status: "blocked",
      message: "Search blocked: no complete acquisition route is ready",
    });

    await user.click(
      await screen.findByRole("button", { name: /force search/i }),
    );

    expect(
      await screen.findByText(
        "Search blocked: no complete acquisition route is ready",
      ),
    ).toBeTruthy();
    expect(
      screen.queryByText(
        "Search accepted — 3 wanted issues queued. Run run-123.",
      ),
    ).toBeNull();
  });

  it("reports a partially accepted force search without claiming full success", async () => {
    const user = userEvent.setup();
    renderWantedWithForceResult({
      success: true,
      status: "partial",
      run_id: "run-partial",
      accepted: 2,
      message: "Search queued 2 Wanted issues; 1 could not be queued",
    });

    await user.click(
      await screen.findByRole("button", { name: /force search/i }),
    );

    expect(await screen.findByText("Search partially accepted")).toBeTruthy();
    expect(
      screen.getByText(
        "Search queued 2 Wanted issues; 1 could not be queued. Run run-partial.",
      ),
    ).toBeTruthy();
  });

  it("reports a failed force search distinctly", async () => {
    const user = userEvent.setup();
    renderWantedWithForceResult({
      success: false,
      status: "failed",
      message: "Search failed to start",
    });

    await user.click(
      await screen.findByRole("button", { name: /force search/i }),
    );

    expect(await screen.findByText("Search failed to start")).toBeTruthy();
    expect(
      screen.queryByText(
        "Search accepted — 3 wanted issues queued. Run run-123.",
      ),
    ).toBeNull();
  });
});
