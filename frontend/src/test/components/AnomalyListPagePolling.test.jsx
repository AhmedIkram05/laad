import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, act } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { SearchProvider } from "../../components/GlobalSearch";

vi.mock("sonner", () => ({
  toast: { error: vi.fn(), success: vi.fn() },
}));

const REFRESH_INTERVAL_MS = 60_000;

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

function entitiesResponse() {
  return Promise.resolve({ ok: true, json: () => Promise.resolve({ entities: [] }) });
}

function anomaliesResponse() {
  return Promise.resolve({ ok: true, json: () => Promise.resolve({ data: [anomaly()] }) });
}

function makeFetch({ anomalies = anomaliesResponse, hangAnomalies = false } = {}) {
  return vi.fn().mockImplementation((url, opts = {}) => {
    if (String(url).includes("/api/analytics/entities")) {
      return entitiesResponse();
    }
    if (hangAnomalies) return new Promise(() => {});
    return anomaliesResponse();
  });
}

async function renderList(fetchImpl) {
  global.fetch = fetchImpl;
  const { default: AnomalyListPage } = await import("../../components/AnomalyListPage");
  return render(
    <MemoryRouter>
      <SearchProvider>
        <AnomalyListPage title="T" subtitle="S" isActive={1} />
      </SearchProvider>
    </MemoryRouter>
  );
}

const anomaliesCalls = (fetchImpl) =>
  fetchImpl.mock.calls.filter(([url]) => String(url).includes("/api/anomalies")).length;

describe("AnomalyListPage auto-refresh", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  it("re-fetches the list on the 60s interval, not before", async () => {
    vi.useFakeTimers();
    const fetchImpl = makeFetch();
    await renderList(fetchImpl);
    // Settle the mount fetch's state updates (findBy* would stall: RTL's
    // waitFor polls with the faked timers).
    await act(async () => {});
    expect(anomaliesCalls(fetchImpl)).toBe(1);

    // 59s in: still only the mount fetch — the interval is 60s, not "soon".
    await act(async () => {
      await vi.advanceTimersByTimeAsync(REFRESH_INTERVAL_MS - 1000);
    });
    expect(anomaliesCalls(fetchImpl)).toBe(1);

    // Crossing the 60s mark triggers exactly one silent refresh.
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1000);
    });
    expect(anomaliesCalls(fetchImpl)).toBe(2);
  });

  it("skips an interval tick while the previous cycle is still in flight", async () => {
    vi.useFakeTimers();
    const fetchImpl = makeFetch({ hangAnomalies: true });
    await renderList(fetchImpl);
    expect(anomaliesCalls(fetchImpl)).toBe(1);

    // Two 60s ticks land while the mount fetch hangs — neither may pile on
    // a new request.
    await act(async () => {
      await vi.advanceTimersByTimeAsync(REFRESH_INTERVAL_MS);
      await vi.advanceTimersByTimeAsync(REFRESH_INTERVAL_MS);
    });
    expect(anomaliesCalls(fetchImpl)).toBe(1);
  });

  it("aborts the in-flight request and stops polling on unmount", async () => {
    vi.useFakeTimers();
    const fetchImpl = makeFetch({ hangAnomalies: true });
    const { unmount } = await renderList(fetchImpl);

    let lastAnomalyOpts = null;
    for (const [url, opts] of fetchImpl.mock.calls) {
      if (String(url).includes("/api/anomalies")) lastAnomalyOpts = opts;
    }
    unmount();
    expect(lastAnomalyOpts.signal.aborted).toBe(true);

    const callsAtUnmount = fetchImpl.mock.calls.length;
    await act(async () => {
      await vi.advanceTimersByTimeAsync(REFRESH_INTERVAL_MS * 2);
    });
    expect(fetchImpl.mock.calls.length).toBe(callsAtUnmount);
  });
});
