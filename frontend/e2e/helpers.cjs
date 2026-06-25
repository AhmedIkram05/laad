// @ts-check
/**
 * Shared Playwright helper functions for LAAD E2E tests.
 */

/**
 * Log in as admin. Call this in `beforeEach` or inline before dashboard tests.
 * @param {import("@playwright/test").Page} page
 */
async function loginAsAdmin(page) {
  await page.goto("/login");
  await page.fill("#username", "admin");
  await page.fill("#password", "admin");
  await page.click("button[type=submit]");
  // Wait for the dashboard to fully render — this confirms:
  // 1. URL changed to /dashboard (React Router pushState)
  // 2. /auth/me completed (user state loaded)
  // 3. Dashboard content rendered (h1 "Anomalies" visible)
  await page.locator("h1").filter({ hasText: "Anomalies" }).waitFor({ state: "visible", timeout: 30_000 });
}

module.exports = { loginAsAdmin };
