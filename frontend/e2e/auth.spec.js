// @ts-check
const { test, expect } = require("@playwright/test");

test.describe("Authentication", () => {
  test("successful login redirects to dashboard", async ({ page }) => {
    await page.goto("/login");

    // Fill in login form
    await page.fill("#username", "admin");
    await page.fill("#password", "admin");

    // Click sign in button
    await page.click("button[type=submit]");

    // Should redirect to dashboard
    await page.waitForURL(/\/dashboard/, { timeout: 15_000 });
    await expect(page.locator("h1")).toContainText("Anomalies");
  });

  test("invalid credentials shows error message", async ({ page }) => {
    await page.goto("/login");

    // Fill in login form with bad password
    await page.fill("#username", "admin");
    await page.fill("#password", "wrongpassword");

    // Click sign in
    await page.click("button[type=submit]");

    // Should show error toast
    await expect(page.locator("text=Login failed")).toBeVisible({ timeout: 10_000 });
  });
});
