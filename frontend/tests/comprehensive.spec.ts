import { test, expect } from "@playwright/test";
import fs from "fs";
import os from "os";
import path from "path";

const GPX = new URL("../../examples/sample_route.gpx", import.meta.url).pathname;
const BAD_XML = new URL("../../gpxsamples/bad-xml.gpx", import.meta.url).pathname;

async function uploadFile(page: import("@playwright/test").Page, filePath: string) {
  await page.getByTestId("drop-zone").locator('input[type="file"]').setInputFiles(filePath);
}

test.describe("comprehensive: full upload flow", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/");
  });

  test("basic upload, preview, generate download", async ({ page }) => {
    await uploadFile(page, GPX);
    await expect(page.getByTestId("route-name")).toBeVisible({ timeout: 30_000 });
    await expect(page.getByTestId("preview-image")).toHaveAttribute("src", /^blob:/, { timeout: 30_000 });
    await page.getByTestId("btn-generate").click();
    await expect(page.getByTestId("download-link")).toBeVisible({ timeout: 60_000 });
    const href = await page.getByTestId("download-link").getAttribute("href");
    expect(href).toMatch(/^blob:/);
  });

  test("layout smart locking: preview → format disabled = png", async ({ page }) => {
    await uploadFile(page, GPX);
    await expect(page.getByTestId("route-name")).toBeVisible({ timeout: 30_000 });

    await page.getByTestId("opt-layout").selectOption("preview");
    await expect(page.getByTestId("opt-format")).toBeDisabled();
    await expect(page.getByTestId("opt-format")).toHaveValue("png");

    await page.getByTestId("opt-layout").selectOption("strip");
    await expect(page.getByTestId("opt-format")).toBeDisabled();
    await expect(page.getByTestId("opt-format")).toHaveValue("png");

    await page.getByTestId("opt-layout").selectOption("portrait");
    await expect(page.getByTestId("opt-format")).toBeEnabled();
  });

  test("options visibility: portrait shows paper + lanes; preview hides them", async ({ page }) => {
    await uploadFile(page, GPX);
    await expect(page.getByTestId("route-name")).toBeVisible({ timeout: 30_000 });

    // portrait (default) — paper and lanes visible
    await expect(page.getByTestId("opt-paper")).toBeVisible();
    await expect(page.getByTestId("opt-lanes")).toBeVisible();

    // switch to preview — paper and lanes hidden
    await page.getByTestId("opt-layout").selectOption("preview");
    await expect(page.getByTestId("opt-paper")).not.toBeVisible();
    await expect(page.getByTestId("opt-lanes")).not.toBeVisible();
  });

  test("generate landscape PDF", async ({ page }) => {
    await uploadFile(page, GPX);
    await expect(page.getByTestId("route-name")).toBeVisible({ timeout: 30_000 });
    await page.getByTestId("opt-layout").selectOption("landscape");
    await page.getByTestId("btn-generate").click();
    const link = page.getByTestId("download-link");
    await expect(link).toBeVisible({ timeout: 60_000 });
    const download = await link.getAttribute("download");
    expect(download).toMatch(/\.pdf$/i);
  });

  test("generate preview PNG — result shown inline", async ({ page }) => {
    await uploadFile(page, GPX);
    await expect(page.getByTestId("route-name")).toBeVisible({ timeout: 30_000 });
    await page.getByTestId("opt-layout").selectOption("preview");
    await page.getByTestId("btn-generate").click();
    // PNG result replaces the preview image inline; no download link
    await expect(page.getByTestId("preview-image")).toHaveAttribute("src", /^blob:/, { timeout: 60_000 });
    await expect(page.getByTestId("download-link")).not.toBeVisible();
  });

  test("re-upload via compact drop zone", async ({ page }) => {
    await uploadFile(page, GPX);
    await expect(page.getByTestId("route-name")).toBeVisible({ timeout: 30_000 });

    // Upload again via the compact "Upload different file" link in the header
    await page.getByTestId("upload-different").locator("..").locator('input[type="file"]').setInputFiles(GPX);
    // Route info refreshes (still visible)
    await expect(page.getByTestId("route-name")).toBeVisible({ timeout: 30_000 });
  });

  test("settings popover: save API key persists in localStorage", async ({ page }) => {
    await page.goto("/");
    await page.getByTestId("btn-settings").click();
    await page.getByTestId("input-api-key").fill("test-key-123");
    await page.getByRole("button", { name: /save/i }).click();
    await expect(page.getByRole("button", { name: /saved/i })).toBeVisible();

    // Check localStorage
    const stored = await page.evaluate(() => localStorage.getItem("gpxsheet-api-key"));
    expect(stored).toBe("test-key-123");
  });

  test("error: bad-xml.gpx shows analysis failure message", async ({ page }) => {
    await uploadFile(page, BAD_XML);
    // Either the analyze error banner or a submit error appears
    await expect(
      page.locator("text=/failed|error|invalid/i").first()
    ).toBeVisible({ timeout: 30_000 });
  });

  test("error: non-GPX file rejected client-side", async ({ page }) => {
    // Create a temp .txt file
    const tmp = path.join(os.tmpdir(), "test-reject.txt");
    fs.writeFileSync(tmp, "not a gpx file");

    // The DropZone isGpx check should reject it — page stays on idle, no route-name appears
    await page.getByTestId("drop-zone").locator('input[type="file"]').setInputFiles(tmp);

    // Drop zone still present (we're still in idle phase)
    await expect(page.getByTestId("drop-zone")).toBeVisible();
    // No route-name means no API call was made
    await expect(page.getByTestId("route-name")).not.toBeVisible();
  });
});
