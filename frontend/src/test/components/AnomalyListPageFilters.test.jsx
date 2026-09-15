import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, waitFor, fireEvent, act } from "@testing-library/react";
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

const ENTITIES = [{ atm_id: "ATM-GB-0001" }, { atm_id: "ATM-GB-0002" }, { atm_id: "ATM-SERVER-01" }];

function makeFetch({ anomalies, failStar = false } = {}) {
  return vi.fn().mockImplementation((url) => {
    if (String(url).includes("/api/analytics/entities")) {
      return Promise.resolve({ ok: true, json: () => Promise.resolve({ entities: ENTITIES }) });
    }
    if (String(url).includes("/star")) {
      if (failStar) return Promise.resolve({ ok: false, status: 500 });
      return Promise.resolve({ ok: true, json: () => Promise.resolve({}) });
    }
    if (String(url).includes("/resolve")) {
      return Promise.resolve({ ok: true, json: () => Promise.resolve({}) });
    }
    if (String(url).includes("/api/anomalies")) {
      return Promise.resolve({ ok: true, json: () => Promise.resolve({ data: anomalies }) });
    }
    return Promise.resolve({ ok: true, json: () => Promise.resolve({}) });
  });
}

async function renderList(anomalies, props = {}) {
  const { default: AnomalyListPage } = await import("../../components/AnomalyListPage");
  return render(
    <MemoryRouter>
      <SearchProvider>
        <AnomalyListPage title="T" subtitle="S" isActive={1} {...props} />
      </SearchProvider>
    </MemoryRouter>
  );
}

function comboboxes() {
  return screen.getAllByRole("combobox");
}

async function selectOption(comboboxIndex, optionText) {
  fireEvent.click(comboboxes()[comboboxIndex]);
  const option = await screen.findByRole("option", { name: optionText });
  fireEvent.click(option);
}

describe("AnomalyListPage filters", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    global.fetch = makeFetch({ anomalies: [anomaly({ id: 1 }), anomaly({ id: 2, title: "Cash Low" })] });
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("star keeps other anomalies unchanged", async () => {
    await renderList([anomaly({ id: 1 }), anomaly({ id: 2, title: "Cash Low" })]);
    await screen.findByText("Cash Low");
    fireEvent.click(screen.getAllByLabelText("Star anomaly")[0]);
    await waitFor(() => {
      expect(screen.getByLabelText("Unstar anomaly")).toBeDefined();
      expect(screen.getByText("Cash Low")).toBeDefined();
    });
  });

  it("renders fallbacks for missing title/severity/atm", async () => {
    global.fetch = makeFetch({
      anomalies: [anomaly({ id: 9, title: undefined, severity: undefined, atm_id: undefined })],
    });
    await renderList([anomaly({ id: 9, title: undefined, severity: undefined, atm_id: undefined })]);
    await waitFor(() => {
      expect(screen.getAllByText("Unknown")).toHaveLength(2);
      expect(screen.getByText("SERVER")).toBeDefined();
    });
  });

  it("changes sort and shows Clear all, then clears", async () => {
    await renderList([anomaly({ id: 1 })]);
    await screen.findByText("Network Timeout");
    await selectOption(0, "Most Recent");
    await waitFor(() => {
      expect(global.fetch.mock.calls.some(([url]) => String(url).includes("sort_by=detected_at"))).toBe(true);
      expect(screen.getByText("Clear all")).toBeDefined();
    });
    fireEvent.click(screen.getByText("Clear all"));
    await waitFor(() => {
      expect(screen.queryByText("Clear all")).toBeNull();
    });
  });

  it("filters by entity type and specific ATM", async () => {
    await renderList([anomaly({ id: 1 })]);
    await screen.findByText("Network Timeout");
    await selectOption(1, "ATMs Only");
    await waitFor(() => {
      expect(global.fetch.mock.calls.some(([url]) => String(url).includes("entity_type=atm"))).toBe(true);
    });
    await selectOption(1, "Servers Only");
    await waitFor(() => {
      expect(global.fetch.mock.calls.some(([url]) => String(url).includes("entity_type=server"))).toBe(true);
    });
    await selectOption(1, "ATM-GB-0002");
    await waitFor(() => {
      expect(global.fetch.mock.calls.some(([url]) => String(url).includes("atm_id=ATM-GB-0002"))).toBe(true);
    });
    await selectOption(1, "All Entities");
    await waitFor(() => {
      expect(screen.queryByText("Clear all")).toBeNull();
    });
  });

  it("filters by anomaly type, severity and detector", async () => {
    await renderList([anomaly({ id: 1 })]);
    await screen.findByText("Network Timeout");
    await selectOption(2, "A1 - Network Timeout");
    await selectOption(3, "CRITICAL");
    await selectOption(4, "ML Ensemble");
    await waitFor(() => {
      const urls = global.fetch.mock.calls.map(([url]) => String(url));
      expect(urls.some((u) => u.includes("anomaly_type=A1"))).toBe(true);
      expect(urls.some((u) => u.includes("severity=CRITICAL"))).toBe(true);
      expect(urls.some((u) => u.includes("detection_source=ML_ENSEMBLE"))).toBe(true);
    });
  });

  it("shows server entities in entity dropdown", async () => {
    await renderList([anomaly({ id: 1 })]);
    await screen.findByText("Network Timeout");
    fireEvent.click(comboboxes()[1]);
    expect(await screen.findByRole("option", { name: "ATM-SERVER-01" })).toBeDefined();
  });

  it("First/Last pagination buttons work", async () => {
    const many = Array.from({ length: 25 }, (_, i) => anomaly({ id: i + 1, title: `Item ${i + 1}` }));
    global.fetch = makeFetch({ anomalies: many });
    await renderList(many);
    await screen.findByText("Item 1");
    fireEvent.click(screen.getByText("Last"));
    await waitFor(() => {
      expect(screen.getByText("Page 2 of 2")).toBeDefined();
      expect(screen.getByText("Item 25")).toBeDefined();
    });
    fireEvent.click(screen.getByText("First"));
    await waitFor(() => {
      expect(screen.getByText("Page 1 of 2")).toBeDefined();
    });
  });

  it("shows Unknown for unparseable timestamps", async () => {
    const badTs = { valueOf() { throw new Error("bad date"); } };
    global.fetch = makeFetch({ anomalies: [anomaly({ id: 1, detected_at: badTs })] });
    await renderList([anomaly({ id: 1, detected_at: badTs })]);
    await waitFor(() => {
      expect(screen.getByText("Unknown")).toBeDefined();
    });
  });

  it("ticks the refresh clock on interval", async () => {
    const setSpy = vi.spyOn(window, "setInterval");
    const clearSpy = vi.spyOn(window, "clearInterval");
    const { unmount } = await renderList([anomaly({ id: 1 })]);
    await screen.findByText("Network Timeout");
    const tick = setSpy.mock.calls.find(([fn, ms]) => ms === 30_000);
    expect(tick).toBeDefined();
    await act(async () => { tick[0](); });
    unmount();
    expect(clearSpy).toHaveBeenCalled();
    setSpy.mockRestore();
    clearSpy.mockRestore();
  });

  it("cancels load on unmount without crashing", async () => {
    let resolveFetch;
    global.fetch = vi.fn().mockImplementation((url) => {
      if (String(url).includes("/api/anomalies")) {
        return new Promise((res) => { resolveFetch = res; });
      }
      return Promise.resolve({ ok: true, json: () => Promise.resolve({ entities: [] }) });
    });
    const { unmount } = await renderList([anomaly({ id: 1 })]);
    unmount();
    await act(async () => {
      resolveFetch({ ok: true, json: () => Promise.resolve({ data: [] }) });
    });
  });
});
