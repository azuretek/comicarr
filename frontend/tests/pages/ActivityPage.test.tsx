import { describe, expect, it } from "vitest";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { server } from "../mocks/server";
import { render, screen, waitFor } from "../test-utils";
import ActivityPage from "@/pages/ActivityPage";

const queueItem = {
  ID: "queue-1",
  series: "Absolute Flash",
  year: "2026",
  filename: "Absolute Flash 013.cbz",
  size: "10 MB",
  issueid: "issue-13",
  comicid: "comic-1",
  link: "",
  status: "Downloading",
  remote_filesize: "10 MB",
  updated_date: "2026-07-10 08:40",
  site: "DDL(GetComics)",
  submit_date: "2026-07-10 08:35",
};

describe("ActivityPage", () => {
  it("filters, sorts, and paginates the live queue through the API", async () => {
    const requests: URL[] = [];
    server.use(
      http.get("/api/downloads/queue", ({ request }) => {
        const url = new URL(request.url);
        requests.push(url);
        const offset = Number(url.searchParams.get("offset") || 0);
        return HttpResponse.json({
          queue: offset === 0 ? [queueItem] : [],
          pagination: {
            total: offset === 0 ? 30 : 20,
            limit: 25,
            offset,
            has_more: offset === 0,
          },
        });
      }),
    );

    const user = userEvent.setup();
    render(<ActivityPage />, { route: "/activity", useMemoryRouter: true });

    await screen.findByText("Absolute Flash");
    await user.type(
      screen.getByRole("textbox", { name: "Filter queue activity" }),
      "flash",
    );
    await waitFor(() => {
      expect(
        requests.some((url) => url.searchParams.get("q") === "flash"),
      ).toBe(true);
    });

    await user.click(screen.getByRole("button", { name: /Updated/ }));
    await waitFor(() => {
      expect(
        requests.some(
          (url) =>
            url.searchParams.get("sort") === "updated" &&
            url.searchParams.get("order") === "asc",
        ),
      ).toBe(true);
    });

    await user.click(screen.getByRole("button", { name: "Next" }));
    await waitFor(() => {
      expect(
        requests.some((url) => url.searchParams.get("offset") === "25"),
      ).toBe(true);
    });
    await user.click(screen.getByRole("button", { name: "Previous" }));
    await waitFor(() => {
      expect(requests.at(-1)?.searchParams.get("offset")).toBe("0");
    });
  });

  it("uses the shared table for history with newest-first defaults", async () => {
    let historyRequest: URL | undefined;
    server.use(
      http.get("/api/downloads/history", ({ request }) => {
        historyRequest = new URL(request.url);
        return HttpResponse.json({
          history: [
            {
              IssueID: "issue-13",
              ComicName: "Absolute Flash",
              Issue_Number: "13",
              Size: 0,
              DateAdded: "2026-07-10 08:40:00",
              Status: "Post-Processed",
              FolderName: "",
              ComicID: "comic-1",
              Provider: "NZBGeek",
            },
          ],
          pagination: { total: 1, limit: 25, offset: 0, has_more: false },
        });
      }),
    );

    const user = userEvent.setup();
    render(<ActivityPage />, {
      route: "/activity?view=history",
      useMemoryRouter: true,
    });

    await screen.findByText("Absolute Flash");
    expect(historyRequest?.searchParams.get("sort")).toBe("date");
    expect(historyRequest?.searchParams.get("order")).toBe("desc");
    expect(screen.getByRole("button", { name: /Date/ })).toBeTruthy();
    await user.type(
      screen.getByRole("textbox", { name: "Filter download history" }),
      "nzb",
    );
    await waitFor(() => {
      expect(historyRequest?.searchParams.get("q")).toBe("nzb");
    });
  });
});
