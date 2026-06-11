import { test, expect } from "@playwright/test";

const GPX = new URL("../../examples/sample_route.gpx", import.meta.url).pathname;

test("smoke: upload GPX, see stats and preview, generate, download", async ({ page }) => {
  // Log browser console and failed requests for debugging
  const logs: string[] = [];
  page.on("console", (msg) => logs.push(`[${msg.type()}] ${msg.text()}`));
  page.on("requestfailed", (req) => logs.push(`[REQFAIL] ${req.method()} ${req.url()} — ${req.failure()?.errorText}`));
  page.on("request", (req) => { if (req.url().includes("/v1/")) logs.push(`[REQ] ${req.method()} ${req.url()}`); });
  page.on("response", (res) => { if (res.url().includes("/v1/")) logs.push(`[RES] ${res.status()} ${res.url()}`); });

  await page.goto("/");

  // Drop zone visible
  await expect(page.getByTestId("drop-zone")).toBeVisible();

  // Upload file via the hidden file input
  await page.getByTestId("drop-zone").locator('input[type="file"]').setInputFiles(GPX);
  await page.waitForTimeout(2000); // brief pause for requests to fire

  // Route name and stats appear (long timeout: EagerRunner renders synchronously, CI cold start is slow)
  await expect(page.getByTestId("route-name")).toBeVisible({ timeout: 90_000 }).catch((e) => {
    console.log("=== NETWORK LOG ===");
    logs.forEach((l) => console.log(l));
    throw e;
  });
  await expect(page.getByTestId("route-stats")).toBeVisible();

  // Preview image loads
  const preview = page.getByTestId("preview-image");
  await expect(preview).toBeVisible({ timeout: 90_000 });
  await expect(preview).toHaveAttribute("src", /^blob:/);

  // Generate
  await page.getByTestId("btn-generate").click();

  // Download link appears
  await expect(page.getByTestId("download-link")).toBeVisible({ timeout: 90_000 });
});
