import userEvent from "@testing-library/user-event";
import { createElement } from "react";
import { describe, expect, it } from "vitest";
import { http, HttpResponse } from "msw";
import { server } from "../mocks/server";
import { render, screen } from "../test-utils";
import { prepareConfigSaveData } from "@/lib/configSave";
import { formatAppVersion } from "@/lib/version";
import SettingsPage from "@/pages/SettingsPage";

describe("prepareConfigSaveData", () => {
  it("omits blank redacted secrets and raw API key values from saves", () => {
    const saveData = prepareConfigSaveData(
      {
        api_key: "do-not-send",
        ai_api_key: "",
        comicvine_api: "",
        mal_client_id: "",
        prowl_keys: "",
        slack_webhook_url: "",
        mattermost_webhook_url: "",
        discord_webhook_url: "",
        comic_dir: "/comics",
      },
      {
        ai_api_key_set: true,
        comicvine_api_set: true,
        mal_client_id_set: true,
        prowl_keys_set: true,
        slack_webhook_url_set: true,
        mattermost_webhook_url_set: true,
        discord_webhook_url_set: true,
      },
    );

    expect(saveData).toEqual({ comic_dir: "/comics" });
  });

  it("keeps explicit replacement secret values", () => {
    const saveData = prepareConfigSaveData(
      {
        api_key: "do-not-send",
        comicvine_api: "x".repeat(40),
        discord_webhook_url: "https://discord.com/api/webhooks/new",
      },
      {
        comicvine_api_set: true,
        discord_webhook_url_set: true,
      },
    );

    expect(saveData).toEqual({
      comicvine_api: "x".repeat(40),
      discord_webhook_url: "https://discord.com/api/webhooks/new",
    });
  });
});

describe("SettingsPage", () => {
  it("opens the acquisition operator surface from Settings", async () => {
    server.use(
      http.get("/api/search/health", () =>
        HttpResponse.json({
          viable_route: true,
          maintenance: { blocked: false, drained: true, active_leases: 0 },
          routes: {},
          workers: {},
          acquisition: {},
        }),
      ),
      http.get("/api/system/diagnostics", () =>
        HttpResponse.json({
          build: { id: "test-build", commit: "abc1234", verified: true },
        }),
      ),
    );
    const user = userEvent.setup();

    render(createElement(SettingsPage));

    expect(await screen.findByText("Settings")).toBeTruthy();
    await user.click(screen.getAllByRole("button", { name: "Acquisition" })[0]);

    expect(await screen.findByText("Acquisition health")).toBeTruthy();
    expect(screen.getByText("Evidence-driven repair")).toBeTruthy();
  });
  it("shows the package release version even when the API reports a different one", async () => {
    // Regression for #412: Settings/About must not echo backend config.version
    // when that field is a git SHA or stale install metadata.
    server.use(
      http.get("/api/config", () =>
        HttpResponse.json({
          version: "0.19.13",
          config_path: "/config/config.ini",
          data_dir: "/data",
          python_version: "3.12.0",
        }),
      ),
    );
    const user = userEvent.setup();

    render(createElement(SettingsPage));

    expect(
      await screen.findByText(`comicarr ${formatAppVersion()}`, {
        exact: false,
      }),
    ).toBeTruthy();
    expect(screen.queryByText(/0\.19\.13/)).toBeNull();

    await user.click(screen.getAllByRole("button", { name: "About" })[0]);
    expect(await screen.findByText(formatAppVersion(false))).toBeTruthy();
    expect(screen.queryByText("0.19.13")).toBeNull();
  });

  it("shows the Updates group with toggles, diagnostics, and Check now", async () => {
    server.use(
      http.get("/api/config", () =>
        HttpResponse.json({
          check_github: true,
          announce_releases: false,
          config_path: "/config/config.ini",
          data_dir: "/data",
          python_version: "3.12.0",
        }),
      ),
      http.get("/api/system/version", () =>
        HttpResponse.json({
          release_version: "0.21.0",
          latest_version: "0.22.0",
          update_state: "behind",
          update_reason: null,
          pending_whats_new: null,
        }),
      ),
      http.get("/api/system/whats-new/archive", () =>
        HttpResponse.json({
          sections: [{ version: "0.21.0", bullets: ["notes"] }],
          pending: null,
          current: "0.21.0",
          last_seen: "0.21.0",
        }),
      ),
    );
    const user = userEvent.setup();

    render(createElement(SettingsPage));
    expect(await screen.findByText("Settings")).toBeTruthy();
    await user.click(screen.getAllByRole("button", { name: "About" })[0]);

    expect(await screen.findByText("Updates")).toBeTruthy();
    expect(screen.getByText("Check for updates")).toBeTruthy();
    expect(screen.getByText("Announce releases to notifiers")).toBeTruthy();
    expect(
      await screen.findByText("Update available: 0.21.0 → 0.22.0"),
    ).toBeTruthy();
    expect(screen.getByRole("button", { name: "Check now" })).toBeTruthy();
    // Order: Updates before What's new before build rows.
    const updates = screen.getByText("Updates");
    // SettingGroup title (exact); archive no longer duplicates an h2.
    const whatsNew = screen.getByText("What's new");
    expect(await screen.findByTestId("whats-new-archive-summary")).toBeTruthy();
    const build = screen.getByText("Build / environment");
    expect(
      updates.compareDocumentPosition(whatsNew) &
        Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
    expect(
      whatsNew.compareDocumentPosition(build) &
        Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
    // AUTO_UPDATE must not appear.
    expect(screen.queryByText(/auto.?update/i)).toBeNull();
    // No GitHub/git wording in the operator-facing labels/help in this group.
    expect(screen.queryByText(/GitHub/i)).toBeNull();
  });

  it("shows unknown update reason in operator language", async () => {
    server.use(
      http.get("/api/config", () =>
        HttpResponse.json({
          check_github: false,
          announce_releases: false,
        }),
      ),
      http.get("/api/system/version", () =>
        HttpResponse.json({
          update_state: "unknown",
          update_reason: "unreachable",
        }),
      ),
    );
    const user = userEvent.setup();

    render(createElement(SettingsPage));
    expect(await screen.findByText("Settings")).toBeTruthy();
    await user.click(screen.getAllByRole("button", { name: "About" })[0]);

    expect(
      await screen.findByText("Could not reach the release source"),
    ).toBeTruthy();
  });
});
