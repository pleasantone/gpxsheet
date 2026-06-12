import { test, expect } from "@playwright/test";

const GPX = new URL("../../examples/sample_route.gpx", import.meta.url).pathname;

test("table: switch to Table tab, see inline table + copy buttons", async ({ page, context }) => {
  await context.grantPermissions(["clipboard-read", "clipboard-write"]).catch(() => {});

  await page.goto("/");
  await page.getByTestId("drop-zone").locator('input[type="file"]').setInputFiles(GPX);

  // Switching to the Table tab auto-generates the table (the Generate button is
  // there to re-run after option changes).
  await page.getByTestId("tab-table").click();

  // The table renders inline (no iframe) and matches the app shell.
  const out = page.getByTestId("table-output");
  await expect(out).toBeVisible({ timeout: 90_000 });
  await expect(out.locator("table.gpxtable")).toBeVisible();

  // Offline summary header (route name + stat cards), parity with Sheet mode.
  await expect(page.getByTestId("table-name")).toBeVisible();
  await expect(page.getByTestId("table-stats")).toContainText("Distance");

  // Copy buttons sit above the table and give transient feedback.
  const copyMd = page.getByTestId("copy-markdown");
  await expect(copyMd).toBeEnabled();
  await copyMd.click();
  await expect(copyMd).toHaveText("Copied!");

  // Download buttons sit below the table.
  await expect(page.getByTestId("download-markdown")).toBeVisible();
  const [dl] = await Promise.all([
    page.waitForEvent("download"),
    page.getByTestId("download-html").click(),
  ]);
  expect(dl.suggestedFilename()).toMatch(/\.html$/);
});

test("table: departure box is prefilled from a GPX that has timestamps", async ({ page }) => {
  const TIMED = new URL("../../gpxsamples/basecamp-tracks.gpx", import.meta.url).pathname;
  await page.goto("/");
  await page.getByTestId("drop-zone").locator('input[type="file"]').setInputFiles(TIMED);
  await page.getByTestId("tab-table").click();
  // The box reflects the GPX's own start time; generate after it prefills.
  await expect(page.getByTestId("tbl-departure")).toHaveValue(/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/);
  await page.getByTestId("btn-generate").click();
  await page.getByTestId("table-output").waitFor({ timeout: 90_000 });
  await expect(page.getByTestId("table-output")).toContainText("Departure");
});
