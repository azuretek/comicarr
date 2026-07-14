import { describe, expect, it } from "vitest";
import { waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { server } from "../mocks/server";
import { renderMinimal, screen } from "../test-utils";
import AppStatusBar from "@/components/layout/AppStatusBar";

describe("AppStatusBar", () => {
  it("shows live library, API, and queue status", async () => {
    renderMinimal(<AppStatusBar />);

    await waitFor(() => {
      expect(screen.getByText("10 series")).toBeTruthy();
      expect(screen.getByText("online")).toBeTruthy();
      expect(screen.getByText("2 active")).toBeTruthy();
    });

    expect(screen.queryByText("production")).toBeNull();
    expect(screen.queryByText("healthy")).toBeNull();
  });

  it("reports unavailable services instead of retaining stale placeholder text", async () => {
    server.use(
      http.get("/api/dashboard", () =>
        HttpResponse.json({ detail: "Database unavailable" }, { status: 503 }),
      ),
      http.get("/api/health", () =>
        HttpResponse.json({ detail: "Service unavailable" }, { status: 503 }),
      ),
      http.get("/api/downloads/queue", () =>
        HttpResponse.json({ detail: "Queue unavailable" }, { status: 503 }),
      ),
    );

    renderMinimal(<AppStatusBar />);

    await waitFor(() => {
      expect(screen.getAllByText("unavailable")).toHaveLength(3);
    });
  });
});
