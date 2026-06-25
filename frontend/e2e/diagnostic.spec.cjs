// @ts-check
const { test, expect } = require("@playwright/test");
const { loginAsAdmin } = require("./helpers.cjs");

test.describe("Diagnostic Assistant", () => {
  test("chat interface loads with example queries", async ({ page }) => {
    await loginAsAdmin(page);

    // Navigate to diagnostic page via sidebar click (SPA routing — no full page reload)
    // This avoids re-validating auth from scratch, which causes flakiness with page.goto()
    await page.locator("button", { hasText: "Diagnostic" }).click();

    // Chat tab should be active by default
    await expect(page.locator("text=Try asking about")).toBeVisible({ timeout: 15_000 });

    // Example query buttons should be visible
    await expect(page.locator("text=What does anomaly type A1 mean?")).toBeVisible({ timeout: 5_000 });

    // Input field should be present
    const input = page.locator('input[placeholder*="Ask about ATM"]');
    await expect(input).toBeVisible({ timeout: 5_000 });

    // Send button should be present
    await expect(page.locator("button:has-text('Send')")).toBeVisible({ timeout: 5_000 });
  });
});
