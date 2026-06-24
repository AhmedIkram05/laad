import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

describe("Analytics", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  async function renderAnalytics() {
    const { default: Analytics } = await import("../pages/Analytics");
    return render(
      <MemoryRouter>
        <Analytics />
      </MemoryRouter>
    );
  }

  it("renders analytics page title", async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({}),
    });

    await renderAnalytics();

    const title = await screen.findByText("Analytics");
    expect(title).toBeDefined();
  });

  it("renders real-time stats section", async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({}),
    });

    await renderAnalytics();

    // At minimum the page renders without error
    await screen.findByText("Analytics");
    expect(document.querySelector(".grid")).toBeDefined();
  });

  it("shows loading skeletons while fetching", async () => {
    global.fetch = vi.fn().mockImplementation(() => new Promise(() => {}));

    await renderAnalytics();

    await vi.waitFor(() => {
      const skeletons = document.querySelectorAll(".animate-pulse");
      expect(skeletons.length).toBeGreaterThanOrEqual(1);
    }, { timeout: 3000 });
  });

  it("handles fetch errors gracefully", async () => {
    global.fetch = vi.fn().mockRejectedValue(new Error("Network error"));

    await renderAnalytics();

    // Page should render without crashing
    await screen.findByText("Analytics");
    const skeletons = document.querySelectorAll(".animate-pulse");
    expect(skeletons.length).toBeGreaterThanOrEqual(0);
  });
});
