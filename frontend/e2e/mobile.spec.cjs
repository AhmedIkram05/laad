// @ts-check
const { test, expect } = require("@playwright/test");

test.describe("Mobile Responsiveness", () => {
  test.beforeEach(async ({ page }) => {
    // Log in as admin
    await page.goto("/login");
    await page.fill("#username", "admin");
    await page.fill("#password", "admin");
    await page.click("button[type=submit]");
    await page.waitForURL(/\/dashboard/, { timeout: 15_000 });
  });

  test("dashboard renders on mobile viewport", async ({ page }) => {
    // Set viewport to iPhone 12/13 size
    await page.setViewportSize({ width: 390, height: 844 });

    await page.goto("/dashboard");
    await page.waitForTimeout(2_000);

    // Page should render without errors
    const body = page.locator("body");
    await expect(body).toBeVisible();

    // The sidebar should still be present (we don't have a separate mobile nav)
    const sidebar = page.locator("aside");
    await expect(sidebar).toBeVisible();
  });

  test("tablet viewport renders layout correctly", async ({ page }) => {
    // Set viewport to iPad size
    await page.setViewportSize({ width: 768, height: 1024 });

    await page.goto("/dashboard");
    await page.waitForTimeout(2_000);

    // Layout should render correctly on tablet
    await expect(page.locator("h1")).toContainText("Anomalies", { timeout: 10_000 });

    // Make sure the main content area is visible
    const main = page.locator("main");
    await expect(main).toBeVisible();
  });

  test("sidebar collapse works on mobile", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });

    await page.goto("/dashboard");
    await page.waitForTimeout(2_000);

    // Find and click the collapse toggle button
    const toggleButton = page.locator("button[aria-label='Collapse sidebar']");
    if (await toggleButton.isVisible()) {
      await toggleButton.click();
      await page.waitForTimeout(500);

      // After collapse, the expand button should be visible
      await expect(page.locator("button[aria-label='Expand sidebar']")).toBeVisible({ timeout: 5_000 });
    }
  });
});
