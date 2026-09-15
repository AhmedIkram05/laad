import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor, fireEvent, act } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

vi.mock("chart.js", () => ({
  Chart: { register: vi.fn() },
  CategoryScale: {},
  LinearScale: {},
  PointElement: {},
  LineElement: {},
  BarElement: {},
  ArcElement: {},
  Title: {},
  Tooltip: {},
  Legend: {},
  Filler: {},
}));

vi.mock("react-chartjs-2", () => {
  const React = require("react");
  return {
    Bar: ({ data }) =>
      React.createElement("div", { "data-testid": "bar-chart" }, JSON.stringify(data)),
    Line: ({ data }) =>
      React.createElement("div", { "data-testid": "line-chart" }, JSON.stringify(data)),
    Doughnut: ({ data }) =>
      React.createElement("div", { "data-testid": "doughnut-chart" }, JSON.stringify(data)),
  };
});

vi.mock("sonner", () => ({
  toast: { error: vi.fn(), success: vi.fn() },
}));

const realtime = {
  events_by_source: { ATM_APP: 100 },
  anomaly_types: {},
  unique_atms: 5,
};

const events = {
  time_series: [
    { bucket_start: "2024-01-15T10:00:00Z", sources: { ATM_APP: 50 } },
    { bucket_start: "2024-01-15T10:30:00Z", sources: { ATM_APP: 60 } },
  ],
};

function makeFetch(overrides = {}) {
  return vi.fn().mockImplementation((url) => {
    if (url.includes("/api/insights/stats/realtime")) {
      return Promise.resolve({ ok: true, json: () => Promise.resolve(overrides.realtime ?? realtime) });
    }
    if (url.includes("/api/insights/events")) {
      return Promise.resolve({ ok: true, json: () => Promise.resolve(overrides.events ?? events) });
    }
    if (url.includes("/api/insights/metrics?")) {
      return Promise.resolve({ ok: true, json: () => Promise.resolve(overrides.metrics ?? { time_series: [] }) });
    }
    if (url.includes("/api/insights/metrics/list")) {
      return Promise.resolve({ ok: true, json: () => Promise.resolve(overrides.metricsList ?? { metrics: [] }) });
    }
    return Promise.resolve({ ok: true, json: () => Promise.resolve({}) });
  });
}

async function renderAnalytics(overrides = {}) {
  global.fetch = makeFetch(overrides);
  const { default: Analytics } = await import("../../pages/Analytics");
  return render(
    <MemoryRouter>
      <Analytics />
    </MemoryRouter>
  );
}

async function chooseOption(comboboxIndex, optionName) {
  fireEvent.click(screen.getAllByRole("combobox")[comboboxIndex]);
  fireEvent.click(await screen.findByRole("option", { name: optionName }));
}

describe("Analytics branches", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("selects All Time range and refetches with hours=0", async () => {
    await renderAnalytics();
    await screen.findByTestId("bar-chart");
    await chooseOption(0, "All Time");
    await waitFor(() => {
      expect(global.fetch.mock.calls.some(([url]) => String(url).includes("hours=0"))).toBe(true);
    });
    const data = JSON.parse(screen.getByTestId("bar-chart").textContent);
    expect(data.labels.length).toBe(2);
    data.labels.forEach((label) => expect(label.includes(":")).toBe(false));
  });

  it("selects 7 Days range for full date-time labels", async () => {
    await renderAnalytics();
    await screen.findByTestId("bar-chart");
    await chooseOption(0, "7 Days");
    await waitFor(() => {
      expect(global.fetch.mock.calls.some(([url]) => String(url).includes("hours=168"))).toBe(true);
    });
    expect(screen.getByTestId("bar-chart")).toBeDefined();
  });

  it("normalises metric names with empty segments", async () => {
    await renderAnalytics({ metricsList: { metrics: ["cpu__usage"] } });
    await waitFor(() => {
      expect(screen.getByText(/CPU\s+Usage x/)).toBeDefined();
    });
  });

  it("emits null for buckets missing a selected metric", async () => {
    await renderAnalytics({
      metrics: {
        time_series: [
          { bucket_start: "2024-01-15T10:00:00Z", metrics: { KAFKA: { m1: 7 } } },
          { bucket_start: "2024-01-15T10:30:00Z", metrics: { KAFKA: {} } },
        ],
      },
      metricsList: { metrics: ["m1"] },
    });
    await waitFor(() => {
      const data = JSON.parse(screen.getByTestId("line-chart").textContent);
      expect(data.datasets[0].data).toEqual([7, null]);
    });
  });

  it("adds a metric via the Add-metric select", async () => {
    await renderAnalytics({ metricsList: { metrics: ["m1", "m2", "m3", "m4"] } });
    await waitFor(() => {
      expect(screen.getAllByText(/ x$/).length).toBe(3);
    });
    await chooseOption(1, "M4");
    await waitFor(() => {
      expect(screen.getByText("M4 x")).toBeDefined();
    });
  });

  it("falls back for unknown event sources in breakdown", async () => {
    await renderAnalytics({
      realtime: {
        events_by_source: { WEIRD_SOURCE: 7 },
        anomaly_types: {},
        unique_atms: 1,
      },
    });
    await waitFor(() => {
      expect(screen.getByText("WEIRD_SOURCE")).toBeDefined();
      expect(screen.getAllByText("7").length).toBeGreaterThanOrEqual(2);
    });
  });

  it("unmounts cleanly during load", async () => {
    global.fetch = vi.fn().mockImplementation(() => new Promise(() => {}));
    const { default: Analytics } = await import("../../pages/Analytics");
    const { unmount } = render(
      <MemoryRouter>
        <Analytics />
      </MemoryRouter>
    );
    unmount();
    await act(async () => {});
  });
});
