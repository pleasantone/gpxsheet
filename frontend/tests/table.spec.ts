import { test, expect } from "@playwright/test";

const GPX = new URL("../../examples/sample_route.gpx", import.meta.url).pathname;

test("table: switch to Table tab, see the rendered table + copy/download", async ({ page, context }) => {
  await context.grantPermissions(["clipboard-read", "clipboard-write"]).catch(() => {});

  await page.goto("/");
  await page.getByTestId("drop-zone").locator('input[type="file"]').setInputFiles(GPX);

  // Switching to the Table tab auto-generates the table (Generate re-runs it).
  await page.getByTestId("tab-table").click();

  // The table is rendered natively from the structured JSON (a real <table>).
  const out = page.getByTestId("table-output");
  await expect(out).toBeVisible({ timeout: 90_000 });
  await expect(out.locator("table.gpxtable")).toBeVisible();

  // Summary header (route name + stat cards), correct from the JSON.
  await expect(page.getByTestId("table-name")).toBeVisible();
  await expect(page.getByTestId("table-stats")).toContainText("Distance");

  // Copy buttons give transient feedback (built client-side from the JSON).
  const copyMd = page.getByTestId("copy-markdown");
  await expect(copyMd).toBeEnabled();
  await copyMd.click();
  await expect(copyMd).toHaveText("Copied!");

  // Download buttons: Markdown / HTML / JSON, all generated in the browser.
  await expect(page.getByTestId("download-markdown")).toBeVisible();
  const [dlHtml] = await Promise.all([
    page.waitForEvent("download"),
    page.getByTestId("download-html").click(),
  ]);
  expect(dlHtml.suggestedFilename()).toMatch(/\.html$/);
  const [dlJson] = await Promise.all([
    page.waitForEvent("download"),
    page.getByTestId("download-json").click(),
  ]);
  expect(dlJson.suggestedFilename()).toMatch(/\.json$/);
});

test("table: units toggle converts client-side with no re-fetch", async ({ page }) => {
  await page.goto("/");
  await page.getByTestId("drop-zone").locator('input[type="file"]').setInputFiles(GPX);
  await page.getByTestId("tab-table").click();
  await page.getByTestId("table-output").waitFor({ timeout: 90_000 });

  // Imperial by default → miles in the Distance card.
  await expect(page.getByTestId("table-stats")).toContainText("mi");
  // Flipping to metric re-renders instantly from the same JSON (no spinner/job).
  await page.getByTestId("tbl-units").selectOption("metric");
  await expect(page.getByTestId("table-stats")).toContainText("km");
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
  // With a departure, each section header shows a friendly "Departs …" label.
  await expect(page.getByTestId("table-output")).toContainText("Departs");
});
