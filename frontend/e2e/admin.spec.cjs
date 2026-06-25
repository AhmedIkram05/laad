// @ts-check
const { test, expect } = require("@playwright/test");
const { loginAsAdmin } = require("./helpers.cjs");

test.describe("Admin Settings", () => {
  test("admin settings page loads with retention and user creation sections", async ({ page }) => {
    await loginAsAdmin(page);

    // Navigate to admin settings via sidebar click (SPA routing — no full page reload)
    // This avoids re-validating auth from scratch, which causes flakiness with page.goto()
    await page.locator("button", { hasText: "Admin Settings" }).click();

    // Page heading should be visible
    await expect(page.locator("h1")).toContainText("Admin Settings", { timeout: 15_000 });

    // Data Retention card should be present
    await expect(page.locator("text=Data Retention")).toBeVisible({ timeout: 5_000 });

    // Create New User card should be present
    await expect(page.locator("text=Create New User")).toBeVisible({ timeout: 5_000 });

    // Save button should be visible
    await expect(page.locator("button:has-text('Save')")).toBeVisible({ timeout: 5_000 });
  });
});
