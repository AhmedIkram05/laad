import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { SearchProvider } from "../components/GlobalSearch";

vi.mock("../components/AnomalyListPage", () => ({
  default: ({ title }) => <div data-testid="anomaly-list">{title}</div>,
}));

describe("Dashboard", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders AnomalyListPage with title", async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ entities: [] }),
    });

    const { default: Dashboard } = await import("../pages/Dashboard");
    render(
      <MemoryRouter>
        <SearchProvider>
          <Dashboard />
        </SearchProvider>
      </MemoryRouter>
    );
    expect(screen.getByText("Anomalies Detected")).toBeDefined();
  });
});
