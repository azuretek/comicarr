import { expect, test } from "@playwright/test";

const frontendMutationHeaders = {
  "X-Requested-With": "ComicarrFrontend",
};

test("authenticated acquisition diagnostics expose a safe operator contract", async ({
  page,
}) => {
  await page.goto("/settings");

  const [healthResponse, versionResponse, progressResponse] = await Promise.all(
    [
      page.request.get("/api/search/health"),
      page.request.get("/api/system/version"),
      page.request.get("/api/system/migration/progress"),
    ],
  );

  expect(healthResponse.ok()).toBe(true);
  expect(versionResponse.ok()).toBe(true);
  expect(progressResponse.ok()).toBe(true);

  const health = await healthResponse.json();
  expect(health).toEqual(
    expect.objectContaining({
      routes: expect.any(Object),
      viable_route: expect.any(Boolean),
      maintenance: expect.objectContaining({
        blocked: expect.any(Boolean),
        active_leases: expect.any(Number),
      }),
    }),
  );

  const version = await versionResponse.json();
  expect(version.build).toEqual(
    expect.objectContaining({
      id: expect.any(String),
      verified: expect.any(Boolean),
    }),
  );

  const progress = await progressResponse.json();
  expect(progress.reconciliation).toEqual(
    expect.objectContaining({ state: expect.any(String) }),
  );
});

test("acquisition mutations require the session-bound confirmation inputs", async ({
  page,
}) => {
  await page.goto("/settings");

  // This deliberately fails before a series lookup or any durable mutation.
  // It keeps the smoke suite safe on the minimal seeded library while proving
  // that the browser cannot bypass the preview-token/fingerprint boundary.
  const searchConfirm = await page.request.post(
    "/api/series/not-a-real-series/search-missing",
    {
      data: { confirm: true },
      headers: frontendMutationHeaders,
    },
  );
  expect(searchConfirm.status()).toBe(400);
  expect(await searchConfirm.json()).toEqual(
    expect.objectContaining({
      success: false,
      error: expect.stringContaining("preview token"),
    }),
  );

  // The operator-only recovery endpoints must reject incomplete requests
  // instead of creating a repair, releasing a gate, or resuming acquisition.
  const [repairPreview, reconciliationReady, maintenanceAbort] =
    await Promise.all([
      page.request.post("/api/system/acquisition/repair/preview", {
        data: {},
        headers: frontendMutationHeaders,
      }),
      page.request.post("/api/system/acquisition/reconciliation/ready", {
        data: {},
        headers: frontendMutationHeaders,
      }),
      page.request.post("/api/system/acquisition/maintenance/abort", {
        data: {},
        headers: frontendMutationHeaders,
      }),
    ]);

  expect(repairPreview.status()).toBe(400);
  expect(await repairPreview.json()).toEqual(
    expect.objectContaining({
      success: false,
      error: "series_id is required",
    }),
  );

  expect(reconciliationReady.status()).toBe(400);
  expect(await reconciliationReady.json()).toEqual(
    expect.objectContaining({
      success: false,
      error: expect.stringContaining("reconciliation release reason"),
    }),
  );

  expect(maintenanceAbort.status()).toBe(400);
  expect(await maintenanceAbort.json()).toEqual(
    expect.objectContaining({
      success: false,
      error: expect.stringContaining("maintenance abort reason"),
    }),
  );
});
