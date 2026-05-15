/*
 * Playwright Tests for RAG Features
 * ----------------------------------
 * Tests RAG History page, stats widget, and recalibrate functionality.
 */

import { test, expect } from "@playwright/test";

test.describe("RAG Features", () => {
    test.beforeEach(async ({ page }) => {
        await page.goto("http://localhost:5173/login");
        await page.fill('input[name="username"]', "admin");
        await page.fill('input[name="password"]', "admin");
        await page.click('button[type="submit"]');
        await page.waitForURL("http://localhost:5173/dashboard", { timeout: 10000 });
    });

    test("RAG History page loads and displays", async ({ page }) => {
        await page.goto("http://localhost:5173/rag-history");
        await page.waitForURL("http://localhost:5173/rag-history", { timeout: 5000 });

        await expect(page.locator("h1")).toContainText("Query History");
        await expect(page.locator(".rag-history")).toBeVisible();

        const pagination = page.locator(".pagination");
        await expect(pagination).toBeVisible();
        await expect(pagination.locator("button").first()).toBeDisabled();
    });

    test("RAG History navigation link works", async ({ page }) => {
        await page.goto("http://localhost:5173/dashboard");

        await page.click('button:has-text("RAG History")');
        await page.waitForURL("http://localhost:5173/rag-history", { timeout: 5000 });

        await expect(page.locator("h1")).toContainText("Query History");
    });

    test("Diagnostic Assistant shows stats bar", async ({ page }) => {
        await page.goto("http://localhost:5173/diagnostic");
        await page.waitForURL("http://localhost:5173/diagnostic", { timeout: 5000 });

        const statsBar = page.locator(".stats-bar");
        await expect(statsBar).toBeVisible();

        await expect(page.locator(".stat-label:has-text(\"Indexed Chunks\")")).toBeVisible();
        await expect(page.locator(".stat-label:has-text(\"Total Queries\")")).toBeVisible();
        await expect(page.locator(".stat-label:has-text(\"Feedback Samples\")")).toBeVisible();
        await expect(page.locator(".stat-label:has-text(\"Calibrated\")")).toBeVisible();
    });

    test("Diagnostic Assistant shows recalibrate button for admin", async ({ page }) => {
        await page.goto("http://localhost:5173/diagnostic");
        await page.waitForURL("http://localhost:5173/diagnostic", { timeout: 5000 });

        const recalibrateBtn = page.locator("button:has-text(\"Recalibrate\")");
        await expect(recalibrateBtn).toBeVisible();
    });

    test("RAG History page shows empty state when no queries", async ({ page }) => {
        await page.goto("http://localhost:5173/rag-history");
        await page.waitForURL("http://localhost:5173/rag-history", { timeout: 5000 });

        const emptyState = page.locator(".empty");
        await expect(emptyState).toBeVisible();
        await expect(emptyState).toContainText("No queries yet");
    });

    test("RAG History pagination buttons work", async ({ page }) => {
        await page.goto("http://localhost:5173/rag-history");
        await page.waitForURL("http://localhost:5173/rag-history", { timeout: 5000 });

        const prevBtn = page.locator(".pagination button").first();
        const nextBtn = page.locator(".pagination button").last();

        await expect(prevBtn).toBeDisabled();
        await expect(nextBtn).toBeDisabled();
    });
});
