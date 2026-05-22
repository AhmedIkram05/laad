import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { SearchProvider } from "../components/GlobalSearch";

vi.mock("../components/AnomalyListPage", () => ({
  default: ({ title }) => <div data-testid="anomaly-list">{title}</div>,
}));

describe("Completed", () => {
  beforeEach(() => vi.clearAllMocks());

  it("renders with completed title", async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ entities: [] }),
    });

    const { default: Completed } = await import("../pages/Completed");
    render(
      <MemoryRouter>
        <SearchProvider>
          <Completed />
        </SearchProvider>
      </MemoryRouter>
    );
    expect(screen.getByText("Completed Anomalies")).toBeDefined();
  });
});
