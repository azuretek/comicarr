import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  SUPPORT_BUNDLE_FILENAME,
  downloadSupportBundle,
} from "@/lib/supportBundle";
import { ApiError } from "@/lib/api";

const FIXED_ZIP = new Uint8Array([0x50, 0x4b, 0x03, 0x04, 0x00, 0x01]).buffer;

function okHeaders(status: "complete" | "partial" = "complete") {
  return {
    "Content-Type": "application/zip",
    "Content-Disposition": `attachment; filename="${SUPPORT_BUNDLE_FILENAME}"`,
    "X-Comicarr-Support-Bundle-Contract": "1",
    "X-Comicarr-Support-Bundle-Status": status,
  };
}

describe("downloadSupportBundle", () => {
  let createObjectURL: ReturnType<typeof vi.fn>;
  let revokeObjectURL: ReturnType<typeof vi.fn>;
  let click: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    createObjectURL = vi.fn(() => "blob:support-bundle");
    revokeObjectURL = vi.fn();
    click = vi.fn();
    vi.stubGlobal("URL", {
      createObjectURL,
      revokeObjectURL,
    });
    vi.spyOn(document, "createElement").mockImplementation((tag: string) => {
      if (tag === "a") {
        return {
          href: "",
          download: "",
          rel: "",
          style: { display: "" },
          click,
        } as unknown as HTMLAnchorElement;
      }
      return document.createElement(tag);
    });
    vi.spyOn(document.body, "appendChild").mockImplementation(
      (node) => node as Node,
    );
    vi.spyOn(document.body, "removeChild").mockImplementation(
      (node) => node as Node,
    );
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("posts with CSRF header and no body, then downloads fixed filename", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue(
        new Response(FIXED_ZIP, {
          status: 200,
          headers: okHeaders("complete"),
        }),
      );
    vi.stubGlobal("fetch", fetchMock);

    const result = await downloadSupportBundle();
    expect(result).toEqual({ ok: true, status: "complete" });
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/system/support-bundle",
      expect.objectContaining({
        method: "POST",
        credentials: "include",
        headers: expect.objectContaining({
          "X-Requested-With": "ComicarrFrontend",
        }),
      }),
    );
    const init = fetchMock.mock.calls[0][1] as RequestInit;
    expect(init.body).toBeUndefined();
    expect(click).toHaveBeenCalledTimes(1);
    expect(createObjectURL).toHaveBeenCalledTimes(1);
    expect(revokeObjectURL).toHaveBeenCalledWith("blob:support-bundle");
  });

  it("accepts partial status", async () => {
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValue(
          new Response(FIXED_ZIP, {
            status: 200,
            headers: okHeaders("partial"),
          }),
        ),
    );
    const result = await downloadSupportBundle();
    expect(result).toEqual({ ok: true, status: "partial" });
  });

  it("rejects protocol mismatch without download", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(FIXED_ZIP, {
          status: 200,
          headers: {
            ...okHeaders(),
            "X-Comicarr-Support-Bundle-Contract": "2",
          },
        }),
      ),
    );
    const result = await downloadSupportBundle();
    expect(result.ok).toBe(false);
    if (!result.ok) {
      expect(result.error).toBeInstanceOf(ApiError);
      expect(result.error.userMessage).toMatch(/safety checks/);
    }
    expect(click).not.toHaveBeenCalled();
  });

  it("rejects empty and oversized bodies", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(new ArrayBuffer(0), {
          status: 200,
          headers: okHeaders(),
        }),
      ),
    );
    let result = await downloadSupportBundle();
    expect(result.ok).toBe(false);

    const big = new ArrayBuffer(512 * 1024 + 1);
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValue(
          new Response(big, { status: 200, headers: okHeaders() }),
        ),
    );
    result = await downloadSupportBundle();
    expect(result.ok).toBe(false);
    expect(click).not.toHaveBeenCalled();
  });

  it("maps typed JSON errors and Retry-After", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({
            detail:
              "Another support bundle is already being created. Try again in a moment.",
            code: "support_bundle_in_progress",
            retryable: true,
          }),
          {
            status: 409,
            headers: {
              "Content-Type": "application/json",
              "Retry-After": "2",
            },
          },
        ),
      ),
    );
    const result = await downloadSupportBundle();
    expect(result.ok).toBe(false);
    if (!result.ok) {
      expect(result.error.status).toBe(409);
      expect(result.error.isRetryable).toBe(true);
      expect(result.retryAfterSeconds).toBe(2);
      expect(result.error.userMessage).toMatch(/already being created/);
    }
  });

  it("maps 401 and 403 to fixed copy", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(new Response("{}", { status: 401 })),
    );
    let result = await downloadSupportBundle();
    expect(result.ok).toBe(false);
    if (!result.ok) {
      expect(result.error.userMessage).toMatch(/session has expired/);
    }

    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(new Response("{}", { status: 403 })),
    );
    result = await downloadSupportBundle();
    expect(result.ok).toBe(false);
    if (!result.ok) {
      expect(result.error.userMessage).toMatch(/blocked the request/);
    }
  });

  it("handles network interruption", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockRejectedValue(new TypeError("Failed to fetch")),
    );
    const result = await downloadSupportBundle();
    expect(result.ok).toBe(false);
    if (!result.ok) {
      expect(result.error.userMessage).toMatch(/interrupted/);
      expect(result.error.isRetryable).toBe(true);
    }
  });

  it("revokes object URL when download trigger throws", async () => {
    click.mockImplementation(() => {
      throw new Error("click failed");
    });
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValue(
          new Response(FIXED_ZIP, { status: 200, headers: okHeaders() }),
        ),
    );
    const result = await downloadSupportBundle();
    expect(result.ok).toBe(false);
    expect(revokeObjectURL).toHaveBeenCalled();
  });
});
