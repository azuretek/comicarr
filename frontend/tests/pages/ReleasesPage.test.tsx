import { describe, expect, it } from "vitest";
import { waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { server } from "../mocks/server";
import { render, screen } from "../test-utils";
import ReleasesPage from "@/pages/ReleasesPage";

describe("ReleasesPage", () => {
  it("queues a weekly refresh and reports its accepted state", async () => {
    const user = userEvent.setup();
    render(<ReleasesPage />);

    await user.click(
      await screen.findByRole("button", { name: "Refresh releases" }),
    );

    await waitFor(() => {
      expect(
        screen.getByText("Refresh queued — it will start shortly."),
      ).toBeTruthy();
    });
  });

  it("explains when the scheduler is paused instead of claiming a queued refresh", async () => {
    server.use(
      http.post("/api/weekly/refresh", () =>
        HttpResponse.json({
          accepted: false,
          state: "paused",
          error: "Weekly refresh is paused",
        }),
      ),
    );
    const user = userEvent.setup();
    render(<ReleasesPage />);

    await user.click(
      await screen.findByRole("button", { name: "Refresh releases" }),
    );

    expect(await screen.findByText("Weekly refresh is paused")).toBeTruthy();
    expect(screen.queryByText("Refresh queued — it will start shortly.")).toBeNull();
  });

  it("reports a refresh that finishes before the accepted response is rendered", async () => {
    server.use(
      http.get("/api/system/jobs", () =>
        HttpResponse.json({
          jobs: [
            {
              id: "weekly",
              name: "Weekly Pullist",
              next_run_time: "2026-07-12T00:00:00Z",
              trigger: "interval",
              status: "Waiting",
              last_success_timestamp: Date.now() / 1_000,
              last_failure_timestamp: null,
              last_error: null,
            },
          ],
        }),
      ),
    );
    const user = userEvent.setup();
    render(<ReleasesPage />);

    await user.click(
      await screen.findByRole("button", { name: "Refresh releases" }),
    );

    expect(await screen.findByText("Releases refreshed.")).toBeTruthy();
  });
});
