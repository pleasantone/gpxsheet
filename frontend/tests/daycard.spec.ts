import { test, expect } from "@playwright/test";

const GPX = new URL("../../examples/sample_route.gpx", import.meta.url).pathname;

test("day card: switch to the tab, see a stacked card + summary + downloads", async ({
  page,
  context,
}) => {
  await context.grantPermissions(["clipboard-read", "clipboard-write"]).catch(() => {});

  await page.goto("/");
  await page.getByTestId("drop-zone").locator('input[type="file"]').setInputFiles(GPX);

  // Switching to the Day card tab auto-generates the cards (Generate re-runs them).
  await page.getByTestId("tab-daycard").click();

  // Structured cards render — a single-day route gives exactly one card.
  const out = page.getByTestId("daycard-output");
  await expect(out).toBeVisible({ timeout: 90_000 });
  await expect(page.getByTestId("daycard-day-0")).toBeVisible();

  // Offline summary header (route name + stat cards), parity with the other tabs.
  await expect(page.getByTestId("daycard-name")).toBeVisible();
  await expect(page.getByTestId("daycard-stats")).toContainText("Distance");
  await expect(page.getByTestId("daycard-stats")).toContainText("Days");

  // Copy markdown sits above; gives transient feedback.
  const copyMd = page.getByTestId("copy-daycard-md");
  await expect(copyMd).toBeEnabled();
  await copyMd.click();
  await expect(copyMd).toHaveText("Copied!");

  // Download JSON sits below and serializes the in-memory cards client-side.
  const [dl] = await Promise.all([
    page.waitForEvent("download"),
    page.getByTestId("download-daycard-json").click(),
  ]);
  expect(dl.suggestedFilename()).toMatch(/\.json$/);
});

test("day card: a multi-day route renders one card per day", async ({ page }) => {
  const MULTI = new URL("../../gpxsamples/ich-north.gpx", import.meta.url).pathname;
  await page.goto("/");
  await page.getByTestId("drop-zone").locator('input[type="file"]').setInputFiles(MULTI);
  await page.getByTestId("tab-daycard").click();

  await expect(page.getByTestId("daycard-output")).toBeVisible({ timeout: 90_000 });
  // ich-north has multiple <trk> elements → at least two day cards, in order.
  await expect(page.getByTestId("daycard-day-0")).toBeVisible();
  await expect(page.getByTestId("daycard-day-1")).toBeVisible();
});

test("day card: departure box is prefilled from a GPX that has timestamps", async ({ page }) => {
  const TIMED = new URL("../../gpxsamples/basecamp-tracks.gpx", import.meta.url).pathname;
  await page.goto("/");
  await page.getByTestId("drop-zone").locator('input[type="file"]').setInputFiles(TIMED);
  await page.getByTestId("tab-daycard").click();
  // The box reflects the GPX's own start time.
  await expect(page.getByTestId("dc-departure")).toHaveValue(/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/);
});
