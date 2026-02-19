import { defineConfig, devices } from "@playwright/test";

/**
 * Playwright E2E configuration for the TitanFlow dashboard.
 *
 * Tests run against the Next.js dev server (which falls back to standalone
 * mode when Redis is unavailable, letting us test the UI in isolation).
 *
 * Socket.IO / live-data tests intercept HTTP polling at the route level so
 * they don't require a real Redis instance.
 */
export default defineConfig({
  testDir: "./e2e",
  fullyParallel: true,
  /* Fail the build on CI if test.only is left in source. */
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 1 : undefined,
  reporter: [
    ["html", { outputFolder: "playwright-report", open: "never" }],
    ["list"],
  ],
  use: {
    baseURL: "http://localhost:3000",
    trace: "on-first-retry",
    screenshot: "only-on-failure",
    /* Capture video on first retry to help debug flakiness in CI. */
    video: "on-first-retry",
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
    {
      name: "firefox",
      use: { ...devices["Desktop Firefox"] },
    },
    {
      name: "webkit",
      use: { ...devices["Desktop Safari"] },
    },
  ],
  webServer: {
    /* `npm run dev` runs `node server.js` which starts Next.js + Socket.IO */
    command: "npm run dev",
    url: "http://localhost:3000",
    /* Reuse existing server in local dev, always fresh in CI */
    reuseExistingServer: !process.env.CI,
    timeout: 120_000,
  },
});
