import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { SearchProvider } from "../../components/GlobalSearch";

vi.mock("sonner", () => ({
  toast: { error: vi.fn(), success: vi.fn() },
}));

const anomaly = (id, title) => ({
  id,
  title,
  anomaly_type: "A1",
  severity: "CRITICAL",
  atm_id: "ATM-GB-0001",
  detected_at: new Date().toISOString(),
  is_active: 1,
  is_starred: 0,
});

let anomaliesResponse;

function makeFetch() {
  return vi.fn().mockImplementation((url) => {
    const u = String(url);
    if (u.includes("/api/analytics/entities")) {
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve({ entities: [{ atm_id: "ATM-GB-0001" }] }),
      });
    }
    if (u.includes("/api/anomalies")) {
      return Promise.resolve({
        ok: true,
        json: () =>
          Promise.resolve({ data: anomaliesResponse, total: anomaliesResponse.length }),
      });
    }
    return Promise.resolve({ ok: true, json: () => Promise.resolve({}) });
  });
}

async function renderList() {
  const { default: AnomalyListPage } = await import("../../components/AnomalyListPage");
  return render(
    <MemoryRouter>
      <SearchProvider>
        <AnomalyListPage title="T" subtitle="S" isActive={1} />
      </SearchProvider>
    </MemoryRouter>
  );
}

describe("AnomalyListPage page reset on filter change (#17)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    globalThis.fetch = makeFetch();
  });

  it("resets to page 1 when a filter changes while on page N>1", async () => {
    anomaliesResponse = Array.from({ length: 45 }, (_, i) =>
      anomaly(i + 1, `Issue ${i + 1}`)
    );
    await renderList();
    await screen.findByText("Issue 1");

    // Move to page 3 of 3.
    fireEvent.click(screen.getByText("Next"));
    fireEvent.click(screen.getByText("Next"));
    expect(screen.getByText("Page 3 of 3")).toBeDefined();
    expect(screen.getByText("Issue 41")).toBeDefined();

    // Change a filter → the new result set has a single page. Pre-fix this
    // kept page 3 and rendered "No anomalies found." with "Page 3 of 1".
    anomaliesResponse = [anomaly(999, "Only Match")];
    const comboboxes = screen.getAllByRole("combobox");
    fireEvent.click(comboboxes[3]); // Severity select
    fireEvent.click(await screen.findByRole("option", { name: "CRITICAL" }));

    await screen.findByText("Only Match");
    // Single-page result → no pagination block, and no false empty state.
    expect(screen.queryByText(/Page \d+ of \d+/)).toBeNull();
    expect(screen.queryByText("No anomalies found.")).toBeNull();
  });
});
