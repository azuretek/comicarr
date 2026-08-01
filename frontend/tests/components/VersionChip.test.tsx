import { createElement } from "react";
import { describe, expect, it } from "vitest";
import { http, HttpResponse } from "msw";
import userEvent from "@testing-library/user-event";
import { waitFor } from "@testing-library/react";
import { server } from "../mocks/server";
import { render, screen } from "../test-utils";
import { formatAppVersion } from "@/lib/version";
import VersionChip from "@/components/layout/VersionChip";

describe("VersionChip", () => {
  it("renders silent pill without cue when current", async () => {
    server.use(
      http.get("/api/system/version", () =>
        HttpResponse.json({
          update_state: "current",
          latest_version: "0.21.0",
          release_version: "0.21.0",
          install_type: "docker",
        }),
      ),
    );
    render(createElement(VersionChip));
    const pill = await screen.findByLabelText(
      `Version ${formatAppVersion(false)}`,
    );
    expect(pill).toBeTruthy();
    expect(screen.queryByText(/Update available/i)).toBeNull();
  });

  it("shows quiet-dot cue when behind and opens popover", async () => {
    server.use(
      http.get("/api/system/version", () =>
        HttpResponse.json({
          update_state: "behind",
          latest_version: "0.22.0",
          release_version: "0.21.0",
          install_type: "docker",
        }),
      ),
      http.get("/api/system/release-notes", ({ request }) => {
        const url = new URL(request.url);
        expect(url.searchParams.get("through")).toBe("0.22.0");
        return HttpResponse.json({
          sections: [
            {
              version: "0.22.0",
              bullets: ["Brand new remote release note."],
            },
          ],
        });
      }),
    );

    const user = userEvent.setup();
    render(createElement(VersionChip));

    const pill = await screen.findByLabelText(
      `Version ${formatAppVersion(false)}, update available`,
    );
    await user.click(pill);

    expect(await screen.findByText("Update available")).toBeTruthy();
    expect(await screen.findByText("0.22.0")).toBeTruthy();
    expect(
      await screen.findByText(/Brand new remote release note/),
    ).toBeTruthy();
    expect(screen.getByRole("button", { name: /How to update/i })).toBeTruthy();
    const release = screen.getByRole("link", { name: /Release/i });
    expect(release.getAttribute("href")).toBe(
      "https://github.com/frankieramirez/comicarr/releases/tag/v0.22.0",
    );
  });

  it("unknown state has no cue", async () => {
    server.use(
      http.get("/api/system/version", () =>
        HttpResponse.json({
          update_state: "unknown",
          update_reason: "unreachable",
          latest_version: null,
          install_type: "git",
        }),
      ),
    );
    render(createElement(VersionChip));
    await screen.findByLabelText(`Version ${formatAppVersion(false)}`);
    expect(
      screen.queryByLabelText(/update available/i),
    ).toBeNull();
  });

  it("transport failure shows no cue", async () => {
    server.use(
      http.get("/api/system/version", () =>
        HttpResponse.json({ error: "boom" }, { status: 500 }),
      ),
    );
    render(createElement(VersionChip));
    await waitFor(() => {
      expect(
        screen.getByLabelText(`Version ${formatAppVersion(false)}`),
      ).toBeTruthy();
    });
    expect(screen.queryByLabelText(/update available/i)).toBeNull();
  });

  it("How to update reveals docker compose guidance", async () => {
    server.use(
      http.get("/api/system/version", () =>
        HttpResponse.json({
          update_state: "behind",
          latest_version: "0.22.0",
          install_type: "docker",
        }),
      ),
      http.get("/api/system/release-notes", () =>
        HttpResponse.json({ sections: [] }),
      ),
    );
    const user = userEvent.setup();
    render(createElement(VersionChip));
    await user.click(
      await screen.findByLabelText(
        `Version ${formatAppVersion(false)}, update available`,
      ),
    );
    await user.click(screen.getByRole("button", { name: /How to update/i }));
    expect(await screen.findByText(/How to update \(Docker\)/i)).toBeTruthy();
    expect(screen.getByText(/docker compose pull/i)).toBeTruthy();
  });
});
