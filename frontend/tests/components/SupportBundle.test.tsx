import { createElement } from "react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "../test-utils";

import { SupportBundleSection } from "@/components/settings/SupportBundleSection";
import { ApiError } from "@/lib/api";

const downloadMock = vi.fn();

vi.mock("@/lib/supportBundle", () => ({
  downloadSupportBundle: (...args: unknown[]) => downloadMock(...args),
}));

const toastMock = vi.fn();
vi.mock("@/components/ui/toast", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/components/ui/toast")>();
  return {
    ...actual,
    useToast: () => ({ addToast: toastMock }),
  };
});

afterEach(() => {
  downloadMock.mockReset();
  toastMock.mockReset();
});

describe("SupportBundleSection", () => {
  it("opens confirmation and cancels without requesting", async () => {
    const user = userEvent.setup();
    render(createElement(SupportBundleSection));

    await user.click(
      screen.getByRole("button", { name: "Create support bundle" }),
    );
    expect(
      screen.getByRole("heading", { name: "Create a support bundle?" }),
    ).toBeTruthy();
    expect(screen.getByText(/Review the files before attaching/)).toBeTruthy();

    await user.click(screen.getByRole("button", { name: "Cancel" }));
    await waitFor(() =>
      expect(
        screen.queryByRole("heading", { name: "Create a support bundle?" }),
      ).toBeNull(),
    );
    expect(downloadMock).not.toHaveBeenCalled();
  });

  it("creates complete download and announces status", async () => {
    downloadMock.mockResolvedValue({ ok: true, status: "complete" });
    const user = userEvent.setup();
    render(createElement(SupportBundleSection));

    await user.click(
      screen.getByRole("button", { name: "Create support bundle" }),
    );
    await user.click(
      screen.getByRole("button", { name: "Create and download" }),
    );

    await waitFor(() =>
      expect(screen.getByTestId("support-bundle-status").textContent).toMatch(
        /download started\. Review it before sharing/,
      ),
    );
    expect(downloadMock).toHaveBeenCalledTimes(1);
    expect(toastMock).toHaveBeenCalledWith(
      expect.objectContaining({ type: "success" }),
    );
  });

  it("handles partial success with info treatment", async () => {
    downloadMock.mockResolvedValue({ ok: true, status: "partial" });
    const user = userEvent.setup();
    render(createElement(SupportBundleSection));

    await user.click(
      screen.getByRole("button", { name: "Create support bundle" }),
    );
    await user.click(
      screen.getByRole("button", { name: "Create and download" }),
    );

    await waitFor(() =>
      expect(screen.getByTestId("support-bundle-status").textContent).toMatch(
        /some diagnostics unavailable/,
      ),
    );
    expect(toastMock).toHaveBeenCalledWith(
      expect.objectContaining({ type: "info" }),
    );
  });

  it("shows retryable conflict and non-retryable validation failure", async () => {
    const conflict = new ApiError(
      409,
      "Another support bundle is being created. Try again in a moment.",
      { code: "support_bundle_in_progress", retryable: true },
    );
    conflict.isRetryable = true;
    downloadMock.mockResolvedValueOnce({
      ok: false,
      error: conflict,
      retryAfterSeconds: 2,
    });
    const user = userEvent.setup();
    render(createElement(SupportBundleSection));

    await user.click(
      screen.getByRole("button", { name: "Create support bundle" }),
    );
    await user.click(
      screen.getByRole("button", { name: "Create and download" }),
    );

    await waitFor(() =>
      expect(screen.getByTestId("support-bundle-error").textContent).toMatch(
        /being created/,
      ),
    );
    expect(
      screen.getByTestId("support-bundle-error-retry").hasAttribute("disabled"),
    ).toBe(true);

    const validation = new ApiError(
      500,
      "Comicarr stopped the download because the bundle did not pass its safety checks. No file was downloaded.",
      { code: "support_bundle_validation_failed", retryable: false },
    );
    validation.isRetryable = false;
    downloadMock.mockResolvedValueOnce({
      ok: false,
      error: validation,
    });
    await user.click(screen.getByTestId("support-bundle-error-close"));
    await user.click(
      screen.getByRole("button", { name: "Create support bundle" }),
    );
    await user.click(
      screen.getByRole("button", { name: "Create and download" }),
    );
    await waitFor(() =>
      expect(screen.getByTestId("support-bundle-error").textContent).toMatch(
        /safety checks/,
      ),
    );
    expect(screen.queryByTestId("support-bundle-error-retry")).toBeNull();
    expect(screen.getByTestId("support-bundle-error-close")).toBeTruthy();
  });

  it("prevents double submit while creating", async () => {
    let resolveDownload: (value: unknown) => void = () => undefined;
    downloadMock.mockImplementation(
      () =>
        new Promise((resolve) => {
          resolveDownload = resolve;
        }),
    );
    const user = userEvent.setup();
    render(createElement(SupportBundleSection));

    await user.click(
      screen.getByRole("button", { name: "Create support bundle" }),
    );
    await user.click(
      screen.getByRole("button", { name: "Create and download" }),
    );
    await waitFor(() =>
      expect(
        screen
          .getByRole("button", { name: /Creating/ })
          .hasAttribute("disabled"),
      ).toBe(true),
    );
    // Only one in-flight request is issued.
    expect(downloadMock).toHaveBeenCalledTimes(1);
    resolveDownload({ ok: true, status: "complete" });
    await waitFor(() =>
      expect(screen.getByTestId("support-bundle-status").textContent).toMatch(
        /download started/,
      ),
    );
  });

  it("renders Create → Inspect → Share sequence copy", () => {
    render(createElement(SupportBundleSection));
    expect(screen.getByText("1. Create")).toBeTruthy();
    expect(screen.getByText("2. Inspect")).toBeTruthy();
    expect(screen.getByText("3. Share")).toBeTruthy();
    expect(screen.getByText(/does not include your database/i)).toBeTruthy();
  });
});
