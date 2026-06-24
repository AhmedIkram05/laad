// @ts-check
const { chromium } = require("@playwright/test");
const path = require("path");

/**
 * Global setup for Playwright E2E tests.
 *
 * Logs in once as admin, saves authenticated storage state to
 * a fixture file that all tests reuse. This avoids re-logging in
 * for every test (saves ~15s per test).
 */
async function globalSetup() {
  const baseURL = process.env.BASE_URL || "http://localhost:5173";
  const statePath = path.resolve(__dirname, "../storage-state.json");
  const screenshotPath = path.resolve(__dirname, "../global-setup-failure.png");

  const browser = await chromium.launch();
  const page = await browser.newPage();

  console.log(`[global-setup] Logging in at ${baseURL}/login ...`);

  try {
    await page.goto(`${baseURL}/login`, { timeout: 30_000 });

    // Wait for the login form to render
    await page.waitForSelector("#username", { timeout: 10_000 });

    await page.fill("#username", "admin");
    await page.fill("#password", "admin");
    await page.click("button[type=submit]");

    // Wait for the SPA to redirect after successful login
    await page.waitForURL(/\/dashboard/, { timeout: 30_000 });
    console.log("[global-setup] Login successful, saving storage state.");

    await page.context().storageState({ path: statePath });
  } catch (err) {
    console.error("[global-setup] Login failed:", err.message);
    await page.screenshot({ path: screenshotPath, fullPage: true });
    console.error(`[global-setup] Screenshot saved to ${screenshotPath}`);
    // Don't throw — let tests run anyway (they may fail with useful messages)
  } finally {
    await browser.close();
  }
}

module.exports = globalSetup;
