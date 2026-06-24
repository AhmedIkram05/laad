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
  await page.waitForURL(/\/dashboard/, { timeout: 30_000 });
}

module.exports = { loginAsAdmin };
