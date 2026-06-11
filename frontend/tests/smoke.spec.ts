import { test, expect } from "@playwright/test";

const GPX = new URL("../../examples/sample_route.gpx", import.meta.url).pathname;

test("smoke: upload GPX, see stats and preview, generate, download", async ({ page }) => {
  await page.goto("/");

  // Drop zone visible
  await expect(page.getByTestId("drop-zone")).toBeVisible();

  // Upload file via the hidden file input
  await page.getByTestId("drop-zone").locator('input[type="file"]').setInputFiles(GPX);

  // Route name and stats appear
  await expect(page.getByTestId("route-name")).toBeVisible({ timeout: 30_000 });
  await expect(page.getByTestId("route-stats")).toBeVisible();

  // Preview image loads
  const preview = page.getByTestId("preview-image");
  await expect(preview).toBeVisible({ timeout: 30_000 });
  await expect(preview).toHaveAttribute("src", /^blob:/);

  // Generate
  await page.getByTestId("btn-generate").click();

  // Download link appears
  await expect(page.getByTestId("download-link")).toBeVisible({ timeout: 30_000 });
});
