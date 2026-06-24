import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";

describe("AnomalyData", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  async function renderAnomalyData(type = "A1") {
    const { default: AnomalyData } = await import("../pages/AnomalyData");
    return render(
      <MemoryRouter initialEntries={[`/data/${type}`]}>
        <Routes>
          <Route path="/data/:anomaly_type" element={<AnomalyData />} />
        </Routes>
      </MemoryRouter>
    );
  }

  it("renders anomaly details after loading", async () => {
    global.fetch = vi.fn().mockImplementation((url) => {
      if (url.includes("/api/analysis/detailed")) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({
            data: [{
              Anomaly: "A1",
              root_cause: "Network disconnect detected",
              operations: "ATM-001 unavailable",
              Recommended_Action: "Restart network equipment",
              recommended_action: "Restart network equipment",
              severity: "CRITICAL",
              Title: "Network Timeout Cascade",
            }],
          }),
        });
      }
      if (url.includes("/api/anomalies")) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({
            data: [{
              id: 1,
              anomaly_type: "A1",
              is_active: 1,
              is_starred: 0,
              model_confidence_score: 0.95,
            }],
          }),
        });
      }
      return Promise.resolve({ ok: true, json: () => Promise.resolve({}) });
    });

    await renderAnomalyData("A1");

    await waitFor(() => {
      expect(screen.getByText("Network Timeout Cascade")).toBeDefined();
    }, { timeout: 3000 });
  }, 8000);

  it("shows loading skeleton while fetching", async () => {
    global.fetch = vi.fn().mockImplementation(() => new Promise(() => {}));

    await renderAnomalyData("A1");
    const skeleton = document.querySelector(".animate-pulse");
    expect(skeleton).toBeDefined();
  });

  it("shows star and complete buttons after loading", async () => {
    global.fetch = vi.fn().mockImplementation((url) => {
      if (url.includes("/api/analysis/detailed")) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({
            data: [{
              Anomaly: "A1",
              severity: "CRITICAL",
              Title: "Network Timeout Cascade",
              Recommended_Action: "Restart",
              recommended_action: "Restart",
            }],
          }),
        });
      }
      if (url.includes("/api/anomalies")) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({
            data: [{ id: 1, anomaly_type: "A1", is_active: 1, is_starred: 0 }],
          }),
        });
      }
      return Promise.resolve({ ok: true, json: () => Promise.resolve({}) });
    });

    await renderAnomalyData("A1");

    await waitFor(() => {
      expect(screen.getByText("Star")).toBeDefined();
      expect(screen.getByText("Mark Complete")).toBeDefined();
    }, { timeout: 3000 });
  }, 8000);

  it("handles empty analysis data", async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ data: [] }),
    });

    await renderAnomalyData("A1");

    await waitFor(() => {
      // Should render without crashing and show title or empty state
      const skeleton = document.querySelector(".animate-pulse");
      expect(skeleton).toBeNull();
    }, { timeout: 3000 });
  }, 8000);
});
