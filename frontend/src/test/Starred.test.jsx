import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { SearchProvider } from "../components/GlobalSearch";

vi.mock("../components/AnomalyListPage", () => ({
  default: ({ title }) => <div data-testid="anomaly-list">{title}</div>,
}));

describe("Starred", () => {
  beforeEach(() => vi.clearAllMocks());

  it("renders with starred title", async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ entities: [] }),
    });

    const { default: Starred } = await import("../pages/Starred");
    render(
      <MemoryRouter>
        <SearchProvider>
          <Starred />
        </SearchProvider>
      </MemoryRouter>
    );
    expect(screen.getByText("Starred Anomalies")).toBeDefined();
  });
});
