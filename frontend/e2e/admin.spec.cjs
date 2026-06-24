// @ts-check
const { test, expect } = require("@playwright/test");

test.describe("Admin Settings", () => {
  test("admin settings page loads with retention and user creation sections", async ({ page }) => {
    // Start already authenticated (via global-setup storageState)

    // Navigate to admin settings
    await page.goto("/admin/settings");
    await page.waitForURL(/\/admin\/settings/, { timeout: 10_000 });

    // Page heading should be visible
    await expect(page.locator("h1")).toContainText("Admin Settings", { timeout: 10_000 });

    // Data Retention card should be present
    await expect(page.locator("text=Data Retention")).toBeVisible({ timeout: 5_000 });

    // Create New User card should be present
    await expect(page.locator("text=Create New User")).toBeVisible({ timeout: 5_000 });

    // Save button should be visible
    await expect(page.locator("button:has-text('Save')")).toBeVisible({ timeout: 5_000 });
  });
});
