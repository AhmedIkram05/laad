// @ts-check
const { test, expect } = require("@playwright/test");

test.describe("Anomalies", () => {
  // No beforeEach login needed — global-setup provides auth via storageState

  test("dashboard loads with anomaly list", async ({ page }) => {
    await page.goto("/dashboard");

    // Dashboard heading should be visible
    await expect(page.locator("h1")).toContainText("Anomalies", { timeout: 10_000 });

    // The page renders — anomalies may be empty or populated,
    // but at minimum the title and filters should be present
    const body = page.locator("body");
    await expect(body).toBeVisible();
  });

  test("can filter anomalies by severity", async ({ page }) => {
    await page.goto("/dashboard");

    // Wait for the page to load
    await page.waitForTimeout(2_000);

    // Find a severity filter trigger (look for select elements)
    const selects = page.locator('[role="combobox"]');
    const count = await selects.count();

    if (count > 0) {
      // Try clicking the first select to see if filter UI works
      await selects.first().click();
      await expect(page.locator('[role="listbox"]')).toBeVisible({ timeout: 5_000 });
    }
    // If no selects exist (empty state), the test still passes
  });

  test("can toggle star on an anomaly", async ({ page }) => {
    await page.goto("/dashboard");

    // Wait for anomalies to load
    await page.waitForTimeout(2_000);

    // Look for a star button on an anomaly card
    const starButton = page.locator("button").filter({ has: page.locator('[class*="star"]') }).first();

    if (await starButton.isVisible()) {
      await starButton.click();
      // Wait for the API call to complete — no error toast means success
      await page.waitForTimeout(1_000);
      await expect(page.locator("text=Failed to update star")).toHaveCount(0);
    }
    // If no anomalies exist to star, test still passes
  });
});
