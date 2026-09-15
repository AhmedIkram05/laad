import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { SearchProvider } from "../../components/GlobalSearch";

vi.mock("sonner", () => ({
  toast: { error: vi.fn(), success: vi.fn() },
}));

const anomaly = (overrides = {}) => ({
  id: 1,
  title: "Network Timeout",
  anomaly_type: "A1",
  severity: "CRITICAL",
  atm_id: "ATM-GB-0001",
  detected_at: new Date(Date.now() - 5 * 60000).toISOString(),
  is_active: 1,
  is_starred: 0,
  ...overrides,
});

function makeFetch({ anomalies = [anomaly()], entities = [], anomaliesError = null, entitiesError = false, starOk = true, completeOk = true } = {}) {
  return vi.fn().mockImplementation((url, opts = {}) => {
    if (String(url).includes("/api/analytics/entities")) {
      if (entitiesError) return Promise.reject(new Error("entities down"));
      return Promise.resolve({ ok: true, json: () => Promise.resolve({ entities }) });
    }
    if (String(url).includes("/api/anomalies/") && String(url).includes("/star")) {
      if (!starOk) return Promise.resolve({ ok: false, status: 500 });
      return Promise.resolve({ ok: true, json: () => Promise.resolve({}) });
    }
    if (String(url).includes("/api/anomalies/") && String(url).includes("/resolve")) {
      if (!completeOk) return Promise.resolve({ ok: false, status: 500 });
      return Promise.resolve({ ok: true, json: () => Promise.resolve({}) });
    }
    if (String(url).includes("/api/anomalies")) {
      if (anomaliesError === "throw") return Promise.reject(new Error("down"));
      if (anomaliesError) return Promise.resolve({ ok: false, status: 500 });
      return Promise.resolve({ ok: true, json: () => Promise.resolve({ data: anomalies }) });
    }
    return Promise.resolve({ ok: true, json: () => Promise.resolve({}) });
  });
}

async function renderList(fetchImpl, props = {}) {
  global.fetch = fetchImpl;
  const { default: AnomalyListPage } = await import("../../components/AnomalyListPage");
  return render(
    <MemoryRouter>
      <SearchProvider>
        <AnomalyListPage title="T" subtitle="S" isActive={1} {...props} />
      </SearchProvider>
    </MemoryRouter>
  );
}

describe("AnomalyListPage branches", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("toggles star on click", async () => {
    await renderList(makeFetch());
    await screen.findByText("Network Timeout");
    fireEvent.click(screen.getByLabelText("Star anomaly"));
    await waitFor(() => {
      expect(screen.getByLabelText("Unstar anomaly")).toBeDefined();
    });
  });

  it("toasts on star failure", async () => {
    const { toast } = await import("sonner");
    await renderList(makeFetch({ starOk: false }));
    await screen.findByText("Network Timeout");
    fireEvent.click(screen.getByLabelText("Star anomaly"));
    await waitFor(() => {
      expect(toast.error).toHaveBeenCalledWith("Failed to update star status");
    });
  });

  it("toggles completion and reverts on failure", async () => {
    const { toast } = await import("sonner");
    await renderList(makeFetch({ completeOk: false }));
    await screen.findByText("Network Timeout");
    fireEvent.click(screen.getByLabelText("Mark as completed"));
    await waitFor(() => {
      expect(toast.error).toHaveBeenCalledWith("Failed to update completion status");
    });
  });

  it("formats relative times: just now, minutes, hours", async () => {
    const now = Date.now();
    await renderList(makeFetch({
      anomalies: [
        anomaly({ id: 1, title: "JustNow", detected_at: new Date(now - 10 * 1000).toISOString() }),
        anomaly({ id: 2, title: "FiveMin", detected_at: new Date(now - 5 * 60000).toISOString() }),
        anomaly({ id: 3, title: "ThreeHr", detected_at: new Date(now - 3 * 3600000).toISOString() }),
      ],
    }));
    await screen.findByText("JustNow");
    expect(screen.getByText("Just now")).toBeDefined();
    expect(screen.getByText("5m ago")).toBeDefined();
    expect(screen.getByText("3h ago")).toBeDefined();
  });

  it("filters list via search query", async () => {
    await renderList(makeFetch({
      anomalies: [
        anomaly({ id: 1, title: "Network Timeout" }),
        anomaly({ id: 2, title: "Cash Low", anomaly_type: "A2" }),
      ],
    }));
    await screen.findByText("Cash Low");
    fireEvent.change(screen.getByPlaceholderText(/Search anomalies/i), { target: { value: "cash" } });
    await waitFor(() => {
      expect(screen.queryByText("Network Timeout")).toBeNull();
      expect(screen.getByText("Cash Low")).toBeDefined();
    });
  });

  it("paginates beyond 20 items", async () => {
    const many = Array.from({ length: 25 }, (_, i) =>
      anomaly({ id: i + 1, title: `Item ${i + 1}` })
    );
    await renderList(makeFetch({ anomalies: many }));
    await screen.findByText("Item 1");
    expect(screen.getByText("Page 1 of 2")).toBeDefined();
    fireEvent.click(screen.getByText("Next"));
    await waitFor(() => {
      expect(screen.getByText("Page 2 of 2")).toBeDefined();
      expect(screen.getByText("Item 25")).toBeDefined();
    });
    fireEvent.click(screen.getByText("Prev"));
    await waitFor(() => {
      expect(screen.getByText("Page 1 of 2")).toBeDefined();
    });
  });

  it("toasts when entities fetch fails", async () => {
    const { toast } = await import("sonner");
    await renderList(makeFetch({ entitiesError: true }));
    await waitFor(() => {
      expect(toast.error).toHaveBeenCalledWith("Failed to load entities");
    });
  });

  it("shows empty state when anomalies fetch throws", async () => {
    const spy = vi.spyOn(console, "error").mockImplementation(() => {});
    await renderList(makeFetch({ anomaliesError: "throw" }));
    await screen.findByText("No anomalies found.");
    spy.mockRestore();
  });

  it("shows skeletons while loading", async () => {
    global.fetch = vi.fn().mockImplementation(() => new Promise(() => {}));
    const { default: AnomalyListPage } = await import("../../components/AnomalyListPage");
    render(
      <MemoryRouter>
        <SearchProvider>
          <AnomalyListPage title="T" subtitle="S" />
        </SearchProvider>
      </MemoryRouter>
    );
    await waitFor(() => {
      expect(document.querySelectorAll(".animate-pulse").length).toBeGreaterThanOrEqual(1);
    });
  });
});
