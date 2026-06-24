// @ts-check
const { test, expect } = require("@playwright/test");

test.describe("Diagnostic Assistant", () => {
  test("chat interface loads with example queries", async ({ page }) => {
    // Start already authenticated (via global-setup storageState)

    // Navigate to diagnostic page
    await page.goto("/diagnostic");
    await page.waitForURL(/\/diagnostic/, { timeout: 10_000 });

    // Chat tab should be active by default
    await expect(page.locator("text=Try asking about")).toBeVisible({ timeout: 10_000 });

    // Example query buttons should be visible
    await expect(page.locator("text=What does anomaly type A1 mean?")).toBeVisible({ timeout: 5_000 });

    // Input field should be present
    const input = page.locator('input[placeholder*="Ask about ATM"]');
    await expect(input).toBeVisible({ timeout: 5_000 });

    // Send button should be present
    await expect(page.locator("button:has-text('Send')")).toBeVisible({ timeout: 5_000 });
  });
});
