import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { http, HttpResponse } from "msw";
import { server } from "../mocks/server";
import { renderMinimal, screen, waitFor } from "../test-utils";
import { AcquisitionHealthTab } from "@/components/settings/AcquisitionHealthTab";
import { sanitizeAcquisitionMessage } from "@/hooks/useAcquisitionHealth";

const healthFixture = {
  viable_route: true,
  maintenance: {
    blocked: false,
    drained: true,
    active_leases: 0,
    reason: null,
    owner: null,
    run_id: null,
  },
  routes: {
    nzb: {
      ready: true,
      reason: "ready",
      downstream: "sabnzbd",
      client_ready: true,
      path_ready: true,
      restart_safe: true,
      configured_provider_count: 2,
      executable_provider_count: 1,
      attempted_provider_count: 1,
      last_error: "api_key=not-safe-to-show",
    },
    torrent: {
      ready: false,
      reason: "unsupported_restart_correlation",
      downstream: "watchfolder",
      client_ready: true,
      path_ready: true,
      restart_safe: false,
    },
  },
  workers: {
    search: {
      state: "idle",
      alive: true,
      healthy: true,
      last_heartbeat: 1_783_800_000,
    },
    downloader: {
      state: "failed",
      alive: false,
      healthy: false,
      last_error: "token=do-not-render",
    },
  },
  acquisition: {
    search: {
      dispatch: { state: "accepted" },
      completion: { state: "partial" },
      accepted: 4,
      processed: 4,
      matched: 2,
      no_match: 1,
      deferred: 1,
      failed: 0,
      oldest_backlog: 1_783_799_000,
    },
  },
  blocked_producer_count: 1,
};

function installHealthHandlers() {
  server.use(
    http.get("/api/search/health", () => HttpResponse.json(healthFixture)),
    http.get("/api/system/jobs", () =>
      HttpResponse.json({
        jobs: [
          {
            id: "search",
            name: "Auto-Search",
            status: "missed",
            next_run_time: "2026-07-11T18:00:00Z",
            dispatch: { last_error: "password=not-safe-to-show" },
          },
        ],
      }),
    ),
    http.get("/api/system/diagnostics", () =>
      HttpResponse.json({
        build: {
          id: "comicarr-0.18.9-fixed",
          commit: "abc1234",
          release: "0.18.9",
          verified: true,
        },
      }),
    ),
  );
}

describe("AcquisitionHealthTab", () => {
  it("renders operational readiness without exposing diagnostic secrets", async () => {
    installHealthHandlers();

    renderMinimal(<AcquisitionHealthTab />);

    expect(await screen.findByText("comicarr-0.18.9-fixed")).toBeTruthy();
    expect(screen.getByText("Verified build")).toBeTruthy();
    expect(screen.getByText("Auto-Search")).toBeTruthy();
    expect(screen.getByText("unsupported restart correlation")).toBeTruthy();
    expect(screen.getByText("2 configured")).toBeTruthy();
    expect(screen.getByText("1 executable")).toBeTruthy();
    expect(screen.getByText("1 attempted")).toBeTruthy();
    expect(screen.getByText(/api_key=\[redacted\]/)).toBeTruthy();
    expect(screen.queryByText("not-safe-to-show")).toBeNull();
  });

  it("keeps repair preview read-only until an explicit, token-bound confirmation", async () => {
    installHealthHandlers();
    const previewToken = "preview-token-that-must-not-render";
    const confirmation = vi.fn();
    const apply = vi.fn();

    server.use(
      http.post(
        "/api/system/acquisition/repair/preview",
        async ({ request }) => {
          expect(await request.json()).toEqual({ series_id: "160294" });
          return HttpResponse.json({
            run_id: "repair-1",
            preview_token: previewToken,
            fingerprint: "immutable-preview-fingerprint",
            summary: {
              total: 22,
              owned: 18,
              optional_wanted: 2,
              future: 2,
              failed: 0,
              unknown: 0,
              in_flight: 0,
              selected: 18,
            },
            items: [
              {
                entity_key: "issue:1",
                entity_type: "issue",
                entity_id: "1",
                intent: "policy",
                fulfillment: "downloaded",
                reason: "verified_local_file",
                selected: true,
                optional: false,
              },
              {
                entity_key: "issue:2",
                entity_type: "issue",
                entity_id: "2",
                intent: "policy",
                fulfillment: "missing",
                reason: "released_missing",
                selected: false,
                optional: true,
              },
            ],
          });
        },
      ),
      http.post(
        "/api/system/acquisition/repair/repair-1/confirm",
        async ({ request }) => {
          confirmation(await request.json());
          return HttpResponse.json({
            run_id: "repair-1",
            state: "confirmed",
            selected_count: 19,
          });
        },
      ),
      http.post("/api/system/acquisition/repair/repair-1/apply", () => {
        apply();
        return HttpResponse.json({ run_id: "repair-1", state: "completed" });
      }),
      http.get("/api/system/acquisition/repair/repair-1", () =>
        HttpResponse.json({
          run: {
            run_id: "repair-1",
            state: "completed",
            item_count: 22,
            selected_count: 19,
            applied_count: 19,
            conflict_count: 0,
            rollback_count: 0,
            rollback_conflict_count: 0,
          },
          items: [],
        }),
      ),
    );

    renderMinimal(<AcquisitionHealthTab />);
    const user = userEvent.setup();

    await screen.findByText("Acquisition health");
    await user.type(screen.getByLabelText("Series ID"), "160294");
    await user.click(screen.getByRole("button", { name: "Preview repair" }));

    expect(await screen.findByText("Repair preview")).toBeTruthy();
    expect(screen.getByText("18 owned")).toBeTruthy();
    expect(screen.getByText("2 optional Wanted")).toBeTruthy();
    expect(screen.queryByText(previewToken)).toBeNull();
    expect(
      screen.getByRole("button", { name: "Confirm preview" }),
    ).toHaveProperty("disabled", true);

    await user.click(screen.getByLabelText("Select optional issue:2"));
    await user.click(
      screen.getByLabelText(
        "I reviewed this immutable preview and want to freeze it",
      ),
    );
    await user.click(screen.getByRole("button", { name: "Confirm preview" }));

    await waitFor(() => {
      expect(confirmation).toHaveBeenCalledWith({
        preview_token: previewToken,
        fingerprint: "immutable-preview-fingerprint",
        selected_optional_keys: ["issue:2"],
      });
    });
    expect(await screen.findByText("Manifest confirmed")).toBeTruthy();

    await user.click(
      screen.getByRole("button", { name: "Apply confirmed repair" }),
    );
    await waitFor(() => expect(apply).toHaveBeenCalledOnce());
    expect(await screen.findByText("Repair completed")).toBeTruthy();
  });

  it("allows a read-only preview but disables mutation controls during another maintenance operation", async () => {
    installHealthHandlers();
    server.use(
      http.get("/api/search/health", () =>
        HttpResponse.json({
          ...healthFixture,
          maintenance: {
            blocked: true,
            drained: false,
            active_leases: 1,
            reason: "repair in progress",
            run_id: "another-session-run",
          },
        }),
      ),
      http.post("/api/system/acquisition/repair/preview", () =>
        HttpResponse.json({
          run_id: "repair-preview-only",
          preview_token: "session-only-token",
          fingerprint: "preview-fingerprint",
          summary: { total: 1, selected: 0 },
          items: [],
        }),
      ),
    );

    renderMinimal(<AcquisitionHealthTab />);
    const user = userEvent.setup();

    await screen.findByText("Acquisition health");
    await user.type(screen.getByLabelText("Series ID"), "160294");
    await user.click(screen.getByRole("button", { name: "Preview repair" }));
    await screen.findByText("Repair preview");
    await user.click(
      screen.getByLabelText(
        "I reviewed this immutable preview and want to freeze it",
      ),
    );

    expect(
      screen.getByRole("button", { name: "Confirm preview" }),
    ).toHaveProperty("disabled", true);
    expect(
      screen.getByRole("button", { name: "Resume automatic acquisition" }),
    ).toHaveProperty("disabled", true);
  });

  it("redacts credential-like values before rendering operational errors", () => {
    expect(
      sanitizeAcquisitionMessage(
        "SAB api_key=abc123 and token=def456 at https://alice:secret@example.test/path",
      ),
    ).toBe(
      "SAB api_key=[redacted] and token=[redacted] at https://[redacted]@example.test/path",
    );
  });
});
