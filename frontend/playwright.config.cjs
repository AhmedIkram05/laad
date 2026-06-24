// @ts-check
const { defineConfig, devices } = require("@playwright/test");

/**
 * @see https://playwright.dev/docs/test-configuration
 */
module.exports = defineConfig({
  testDir: "./e2e",
  /* Maximum time one test can run for */
  timeout: 30_000,
  expect: {
    timeout: 10_000,
  },
  /* Run tests in files in parallel */
  fullyParallel: true,
  /* Fail the build on CI if you accidentally left test.only in the source code */
  forbidOnly: !!process.env.CI,
  /* Retry on CI only (1 retry) */
  retries: process.env.CI ? 1 : 0,
  /* 2 parallel workers on CI (ubuntu-latest has 2+ vCPUs) */
  workers: process.env.CI ? 2 : undefined,
  /* Reporter to use */
  reporter: [["list"], ["html", { outputFolder: "playwright-report" }]],
  /* Shared settings for all projects */
  use: {
    baseURL: process.env.BASE_URL || "http://localhost:5173",
    trace: "on-first-retry",
    screenshot: "only-on-failure",
  },

  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
});
