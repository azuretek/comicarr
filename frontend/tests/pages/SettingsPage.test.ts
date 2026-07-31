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
});
