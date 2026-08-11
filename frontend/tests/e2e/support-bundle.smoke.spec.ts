import { execFileSync } from "node:child_process";
import { mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

import { expect, test } from "@playwright/test";

import { monitorBrowser } from "./support/browser-monitor";

function inspectZip(body: Buffer) {
  const dir = mkdtempSync(join(tmpdir(), "support-bundle-"));
  const zipPath = join(dir, "comicarr-support-bundle-v1.zip");
  try {
    writeFileSync(zipPath, body);
    const listing = execFileSync("unzip", ["-l", zipPath], {
      encoding: "utf8",
    });
    expect(listing).toContain("README.txt");
    expect(listing).toContain("manifest.json");
    expect(listing).toContain("diagnostics.json");
    execFileSync("unzip", ["-o", zipPath, "-d", dir], { encoding: "utf8" });
    const manifest = JSON.parse(
      readFileSync(join(dir, "manifest.json"), "utf8"),
    );
    return manifest;
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
}

test("Settings → About creates a Support bundle ZIP", async ({
  page,
}, testInfo) => {
  const browserMonitor = monitorBrowser(
    page,
    testInfo.project.use.baseURL as string,
  );

  await page.goto("/settings?section=about");
  await expect(page.getByText("Support bundle", { exact: true })).toBeVisible();
  await expect(page.getByText("1. Create")).toBeVisible();
  await expect(page.getByText("2. Inspect")).toBeVisible();
  await expect(page.getByText("3. Share")).toBeVisible();

  const downloadPromise = page.waitForEvent("download");
  const responsePromise = page.waitForResponse(
    (response) =>
      response.url().includes("/api/system/support-bundle") &&
      response.request().method() === "POST",
  );

  await page.getByRole("button", { name: "Create support bundle" }).click();
  await expect(
    page.getByRole("heading", { name: "Create a support bundle?" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Create and download" }).click();

  const response = await responsePromise;
  expect(response.status()).toBe(200);
  expect(response.headers()["content-type"] || "").toMatch(/zip/i);
  expect(response.headers()["x-comicarr-support-bundle-contract"]).toBe("1");
  expect(["complete", "partial"]).toContain(
    response.headers()["x-comicarr-support-bundle-status"],
  );
  expect(response.headers()["content-disposition"] || "").toContain(
    "comicarr-support-bundle-v1.zip",
  );

  const download = await downloadPromise;
  expect(download.suggestedFilename()).toBe("comicarr-support-bundle-v1.zip");

  const body = Buffer.from(await response.body());
  const manifest = inspectZip(body);
  expect(manifest.operator_review_required).toBe(true);
  expect(manifest.contract_version).toBe(1);
  expect(["complete", "partial"]).toContain(manifest.bundle_status);

  // Sequential second request after completion is allowed.
  const second = await page.request.post("/api/system/support-bundle", {
    headers: { "X-Requested-With": "ComicarrFrontend" },
  });
  expect([200, 409]).toContain(second.status());
  if (second.status() === 409) {
    const json = await second.json();
    expect(json.code).toBe("support_bundle_in_progress");
    expect(json.retryable).toBe(true);
  }

  // Unauthenticated request cannot invoke the endpoint.
  const bare = await page
    .context()
    .browser()!
    .newContext({
      storageState: { cookies: [], origins: [] },
    });
  const bareResp = await bare.request.post("/api/system/support-bundle", {
    headers: { "X-Requested-With": "ComicarrFrontend" },
  });
  expect([401, 403]).toContain(bareResp.status());
  await bare.close();

  // Wrong CSRF header is rejected.
  const csrf = await page.request.post("/api/system/support-bundle", {
    headers: { "X-Requested-With": "NotComicarr" },
  });
  expect(csrf.status()).toBe(403);

  await expect(page.getByTestId("support-bundle-status")).toContainText(
    /download started/i,
  );

  await browserMonitor.expectClean();
});
