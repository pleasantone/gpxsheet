import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./tests",
  timeout: 180_000,
  retries: 1,
  reporter: "list",
  use: {
    baseURL: process.env.BASE_URL ?? "http://localhost:5173",
    screenshot: "only-on-failure",
    video: "retain-on-failure",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
});
