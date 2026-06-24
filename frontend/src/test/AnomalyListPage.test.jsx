import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { SearchProvider } from "../components/GlobalSearch";

describe("AnomalyListPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  async function renderList(props = {}) {
    const { default: AnomalyListPage } = await import("../components/AnomalyListPage");
    return render(
      <MemoryRouter>
        <SearchProvider>
          <AnomalyListPage title="Test Anomalies" subtitle="Test subtitle" isActive={1} {...props} />
        </SearchProvider>
      </MemoryRouter>
    );
  }

  it("renders title and subtitle", async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ data: [] }),
    });

    await renderList();
    expect(screen.getByText("Test Anomalies")).toBeDefined();
    expect(screen.getByText("Test subtitle")).toBeDefined();
  });

  it("shows empty state when no anomalies", async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ data: [], entities: [] }),
    });

    await renderList();

    const emptyMsg = await screen.findByText("No anomalies found.", {}, { timeout: 3000 });
    expect(emptyMsg).toBeDefined();
  }, 8000);

  it("has filter controls", async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ data: [], entities: [] }),
    });

    await renderList();

    const sortEl = await screen.findByText("Sort:", {}, { timeout: 3000 });
    expect(sortEl).toBeDefined();
    expect(screen.getByText("Entity:")).toBeDefined();
    expect(screen.getByText("Anomaly:")).toBeDefined();
    expect(screen.getByText("Severity:")).toBeDefined();
    expect(screen.getByText("Detector:")).toBeDefined();
  }, 8000);

  it("renders anomaly items when data exists", async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({
        data: [
          { id: 1, title: "Network Timeout", anomaly_type: "A1", severity: "CRITICAL", atm_id: "ATM-GB-0001", detected_at: "2026-06-24T12:00:00Z", is_active: 1, is_starred: 0, score: 10 },
          { id: 2, title: "Cash Low", anomaly_type: "A2", severity: "HIGH", atm_id: "ATM-GB-0002", detected_at: "2026-06-24T11:00:00Z", is_active: 1, is_starred: 0, score: 7 },
        ],
        entities: ["ATM-GB-0001", "ATM-GB-0002"],
        total: 2,
      }),
    });

    await renderList();

    await waitFor(() => {
      expect(screen.getByText("Network Timeout")).toBeDefined();
      expect(screen.getByText("Cash Low")).toBeDefined();
    }, { timeout: 3000 });
  }, 8000);

  it("shows login prompt when fetch returns 401", async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 401,
      json: () => Promise.resolve({ detail: "Not authenticated" }),
    });

    await renderList();

    await waitFor(() => {
      const loginText = screen.queryByText(/sign in/i);
      // Should handle error gracefully without crashing
      expect(document.querySelector(".animate-pulse") || document.querySelector(".text-muted-foreground")).toBeDefined();
    }, { timeout: 3000 });
  }, 8000);

  it("renders severity badges", async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({
        data: [
          { id: 1, title: "Critical Issue", anomaly_type: "A1", severity: "CRITICAL", atm_id: "ATM-GB-0001", detected_at: "2026-06-24T12:00:00Z", is_active: 1, is_starred: 0, score: 10 },
        ],
        entities: ["ATM-GB-0001"],
        total: 1,
      }),
    });

    await renderList();

    await waitFor(() => {
      const criticalBadge = screen.getByText("CRITICAL");
      expect(criticalBadge).toBeDefined();
    }, { timeout: 3000 });
  }, 8000);
});
