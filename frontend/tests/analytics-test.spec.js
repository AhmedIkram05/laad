import { test, expect } from '@playwright/test';

test.describe('Analytics Page', () => {
  test.beforeEach(async ({ page }) => {
    // Login first
    await page.goto('http://localhost:5173/');
    await page.fill('#username', 'admin');
    await page.fill('#password', 'admin');
    await page.click('.loginButton--primary');
    
    // Wait for login to complete by checking for navbar container
    await page.waitForSelector('.navbarContainer', { timeout: 10000 });
  });

  test('shows analytics page with chart element', async ({ page }) => {
    // Navigate to Analytics page
    await page.click('text=Analytics');
    await page.waitForURL('http://localhost:5173/analytics');
    
    // Wait for charts container to load - check for the chart wrapper
    await page.waitForSelector('.analyticsPage__chart', { timeout: 10000 });
    
    // Check that the chart container exists (regardless of data)
    const chartContainer = await page.locator('.analyticsPage__chart').isVisible();
    expect(chartContainer).toBeTruthy();
    
    // Check that tab buttons exist and can be switched - use button role for specificity
    const eventsTab = await page.getByRole('button', { name: 'Events' }).isVisible();
    const metricsTab = await page.getByRole('button', { name: 'Metrics' }).isVisible();
    
    expect(eventsTab).toBeTruthy();
    expect(metricsTab).toBeTruthy();
  });

  test('dashboard scroll behavior', async ({ page }) => {
    // Check that sidebar is fixed and main content scrolls
    const sidebar = await page.locator('.navbarContainer');
    const mainContent = await page.locator('.page');
    
    // Get initial positions
    const sidebarPos = await sidebar.boundingBox();
    const mainContentPos = await mainContent.boundingBox();
    
    // Scroll down
    await page.evaluate(() => window.scrollBy(0, 300));
    await page.waitForTimeout(500);
    
    // Check sidebar position hasn't changed (fixed)
    const sidebarPosAfter = await sidebar.boundingBox();
    expect(sidebarPosAfter.x).toBeCloseTo(sidebarPos.x, 1);
    expect(sidebarPosAfter.y).toBeCloseTo(sidebarPos.y, 1);
  });
});