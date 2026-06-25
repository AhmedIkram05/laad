import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor, fireEvent, act, within } from "@testing-library/react";
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

const toastMock = { error: vi.fn(), success: vi.fn() };
vi.mock("sonner", () => ({
  toast: toastMock,
}));

const defaultRealtime = {
  events_by_source: { ATM_APP: 1500, HARDWARE: 800, TERMINAL_HANDLER: 300 },
  anomaly_types: { A1: 10, A2: 5, A3: 2 },
  unique_atms: 42,
};

const defaultEvents = {
  time_series: [
    {
      bucket_start: "2024-01-15T10:00:00Z",
      sources: { ATM_APP: 50, HARDWARE: 30, TERMINAL_HANDLER: 10 },
    },
    {
      bucket_start: "2024-01-15T10:30:00Z",
      sources: { ATM_APP: 60, HARDWARE: 35, TERMINAL_HANDLER: 12 },
    },
  ],
};

const defaultMetrics = {
  time_series: [
    {
      bucket_start: "2024-01-15T10:00:00Z",
      metrics: { KAFKA: { cpu_usage: 75, memory_usage: 60 } },
    },
    {
      bucket_start: "2024-01-15T10:30:00Z",
      metrics: { KAFKA: { cpu_usage: 80, memory_usage: 65 } },
    },
  ],
};

const defaultMetricsList = { metrics: ["cpu_usage", "memory_usage", "disk_io"] };

function makeFetch(overrides = {}) {
  return vi.fn().mockImplementation((url) => {
    if (url.includes("/api/insights/stats/realtime")) {
      if (overrides.realtimeError) {
        return Promise.resolve({ ok: false, status: 500 });
      }
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve(overrides.realtime ?? defaultRealtime),
      });
    }
    if (url.includes("/api/insights/events")) {
      if (overrides.eventsError) {
        return Promise.resolve({ ok: false, status: 500 });
      }
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve(overrides.events ?? defaultEvents),
      });
    }
    if (url.includes("/api/insights/metrics?")) {
      if (overrides.metricsError) {
        return Promise.resolve({ ok: false, status: 500 });
      }
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve(overrides.metrics ?? defaultMetrics),
      });
    }
    if (url.includes("/api/insights/metrics/list")) {
      if (overrides.metricsListError) {
        return Promise.resolve({ ok: false, status: 500 });
      }
      return Promise.resolve({
        ok: true,
        json: () =>
          Promise.resolve(overrides.metricsList ?? defaultMetricsList),
      });
    }
    return Promise.resolve({ ok: true, json: () => Promise.resolve({}) });
  });
}

async function renderComponent(fetchOverrides = {}) {
  global.fetch = makeFetch(fetchOverrides);
  const { default: Analytics } = await import("../pages/Analytics");
  return render(
    <MemoryRouter>
      <Analytics />
    </MemoryRouter>
  );
}

describe("Analytics Coverage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.useRealTimers();
  });

  it("formats numbers with K suffix (>=1000)", async () => {
    await renderComponent({
      realtime: {
        events_by_source: { ATM_APP: 1500, HARDWARE: 200, TERMINAL_HANDLER: 50 },
        anomaly_types: {},
        unique_atms: 42,
      },
    });

    await waitFor(() => {
      expect(screen.getByText("1.8K")).toBeDefined();
    });
  });

  it("formats numbers with M suffix (>=1000000)", async () => {
    await renderComponent({
      realtime: {
        events_by_source: { ATM_APP: 1500000, HARDWARE: 0, TERMINAL_HANDLER: 0 },
        anomaly_types: {},
        unique_atms: 42,
      },
    });

    await waitFor(() => {
      const items = screen.getAllByText("1.5M");
      expect(items.length).toBeGreaterThanOrEqual(1);
    });
  });

  it("formats small numbers without suffix", async () => {
    await renderComponent({
      realtime: {
        events_by_source: { ATM_APP: 42, HARDWARE: 0, TERMINAL_HANDLER: 0 },
        anomaly_types: {},
        unique_atms: 5,
      },
    });

    await waitFor(() => {
      const items = screen.getAllByText("42");
      expect(items.length).toBeGreaterThanOrEqual(1);
      expect(screen.getByText("5")).toBeDefined();
    });
  });

  it("formats zero as '0'", async () => {
    await renderComponent({
      realtime: {
        events_by_source: { ATM_APP: 0 },
        anomaly_types: {},
        unique_atms: 0,
      },
    });

    await waitFor(() => {
      const items = screen.getAllByText("0");
      expect(items.length).toBeGreaterThanOrEqual(1);
    });
  });

  it("renders all stat card titles", async () => {
    await renderComponent();

    await waitFor(() => {
      expect(screen.getByText("Total Events")).toBeDefined();
      expect(screen.getByText("Total Anomalies")).toBeDefined();
      expect(screen.getByText("ATMs & Servers Being Monitored")).toBeDefined();
      expect(screen.getByText("Metric Types")).toBeDefined();
    });
  });

  it("shows correct anomaly count and type count in subtitle", async () => {
    await renderComponent();

    await waitFor(() => {
      // A1:10 + A2:5 + A3:2 = 17
      const items = screen.getAllByText("17");
      expect(items.length).toBeGreaterThanOrEqual(1);
      // 3 anomaly types (A1, A2, A3)
      expect(screen.getByText("3 types detected")).toBeDefined();
    });
  });

  it("renders event source filter badges with display names", async () => {
    await renderComponent();

    await waitFor(() => {
      expect(screen.getByText("ATM Application")).toBeDefined();
      expect(screen.getByText("Hardware Sensor")).toBeDefined();
      expect(screen.getByText("Terminal Handler")).toBeDefined();
    });
  });

  it("removes event source from filter when badge is clicked", async () => {
    await renderComponent();

    await waitFor(() => {
      expect(screen.getByText("3 sources")).toBeDefined();
    });

    // Find the badge specifically (has cursor-pointer class) in the first matching element
    const badges = screen.getAllByText("Hardware Sensor");
    // The badge is the one with cursor-pointer class (first match in the filter area)
    const badge = badges.find(el => el.classList.contains("cursor-pointer"));
    fireEvent.click(badge);

    await waitFor(() => {
      expect(screen.getByText("2 sources")).toBeDefined();
    });
  });

  it("adds event source back when badge clicked again", async () => {
    await renderComponent();

    await waitFor(() => {
      expect(screen.getByText("3 sources")).toBeDefined();
    });

    // Remove HARDWARE
    const badges1 = screen.getAllByText("Hardware Sensor");
    const badge1 = badges1.find(el => el.classList.contains("cursor-pointer"));
    fireEvent.click(badge1);
    await waitFor(() => {
      expect(screen.getByText("2 sources")).toBeDefined();
    });

    // Add HARDWARE back
    const badges2 = screen.getAllByText("Hardware Sensor");
    const badge2 = badges2.find(el => el.classList.contains("cursor-pointer"));
    fireEvent.click(badge2);
    await waitFor(() => {
      expect(screen.getByText("3 sources")).toBeDefined();
    });
  });

  it("renders Bar chart for event volume", async () => {
    await renderComponent();

    await waitFor(() => {
      const bar = screen.getByTestId("bar-chart");
      expect(bar).toBeDefined();
      const data = JSON.parse(bar.textContent);
      expect(data.datasets.length).toBe(3);
      expect(data.labels.length).toBe(2);
    });
  });

  it("renders Line chart for metrics timeline", async () => {
    await renderComponent();

    await waitFor(() => {
      const line = screen.getByTestId("line-chart");
      expect(line).toBeDefined();
      const data = JSON.parse(line.textContent);
      expect(data.datasets.length).toBeGreaterThan(0);
    });
  });

  it("renders Doughnut chart for anomaly distribution", async () => {
    await renderComponent();

    await waitFor(() => {
      const doughnut = screen.getByTestId("doughnut-chart");
      expect(doughnut).toBeDefined();
      const data = JSON.parse(doughnut.textContent);
      expect(data.labels.length).toBe(3);
      expect(data.datasets[0].data).toEqual([10, 5, 2]);
    });
  });

  it("normalises metric names in chart labels (acronym handling)", async () => {
    await renderComponent();

    await waitFor(() => {
      const line = screen.getByTestId("line-chart");
      const data = JSON.parse(line.textContent);
      const labels = data.datasets.map((ds) => ds.label);
      expect(labels.some((l) => l.includes("CPU"))).toBe(true);
    });
  });

  it("shows metric removal badges with 'x' suffix", async () => {
    await renderComponent();

    await waitFor(() => {
      const badges = screen.getAllByText(/ x$/);
      expect(badges.length).toBe(3);
    });
  });

  it("removes metric when badge is clicked", async () => {
    await renderComponent();

    await waitFor(() => {
      const badges = screen.getAllByText(/ x$/);
      expect(badges.length).toBe(3);
    });

    fireEvent.click(screen.getAllByText(/ x$/)[0]);

    await waitFor(() => {
      const badges = screen.getAllByText(/ x$/);
      expect(badges.length).toBe(2);
    });
  });

  it("displays Events by Source Breakdown section", async () => {
    await renderComponent();

    await waitFor(() => {
      expect(screen.getByText("Events by Source Breakdown")).toBeDefined();
    });
  });

  it("formats large source counts in breakdown", async () => {
    await renderComponent();

    await waitFor(() => {
      const items = screen.getAllByText("1.5K");
      expect(items.length).toBeGreaterThanOrEqual(1);
    });
  });

  it("displays Anomaly Type Frequency section", async () => {
    await renderComponent();

    await waitFor(() => {
      expect(screen.getByText("Anomaly Type Frequency")).toBeDefined();
      // normaliseMetricName("A1") -> "A1" (no underscore/slash to split, not an acronym)
      const a1Items = screen.getAllByText("A1");
      expect(a1Items.length).toBeGreaterThanOrEqual(1);
    });
  });

  it("shows empty state when no anomalies detected", async () => {
    await renderComponent({
      realtime: {
        events_by_source: { ATM_APP: 100 },
        anomaly_types: {},
        unique_atms: 5,
      },
    });

    await waitFor(() => {
      expect(
        screen.getByText("No anomalies detected in this period")
      ).toBeDefined();
    });
  });

  it("shows empty state for no event source data", async () => {
    await renderComponent({
      realtime: {
        events_by_source: {},
        anomaly_types: {},
        unique_atms: 0,
      },
    });

    await waitFor(() => {
      expect(screen.getByText("No event data available")).toBeDefined();
    });
  });

  it("shows empty state for no anomaly type data in frequency list", async () => {
    await renderComponent({
      realtime: {
        events_by_source: { ATM_APP: 100 },
        anomaly_types: {},
        unique_atms: 5,
      },
    });

    await waitFor(() => {
      expect(screen.getByText("No anomaly data available")).toBeDefined();
    });
  });

  it("shows toast error when events fetch fails", async () => {
    await renderComponent({ eventsError: true });

    await waitFor(() => {
      expect(toastMock.error).toHaveBeenCalledWith("Failed to load events data");
    });
  });

  it("shows toast error when metrics fetch fails", async () => {
    await renderComponent({ metricsError: true });

    await waitFor(() => {
      expect(toastMock.error).toHaveBeenCalledWith("Failed to load metrics data");
    });
  });

  it("shows toast error on network failure", async () => {
    global.fetch = vi.fn().mockRejectedValue(new Error("Network error"));

    const { default: Analytics } = await import("../pages/Analytics");
    render(
      <MemoryRouter>
        <Analytics />
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(toastMock.error).toHaveBeenCalledWith(
        "Failed to load analytics data"
      );
    });
  });

  it("refresh button triggers additional fetch", async () => {
    global.fetch = makeFetch();

    const { default: Analytics } = await import("../pages/Analytics");
    render(
      <MemoryRouter>
        <Analytics />
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(screen.getByText("Refresh")).toBeDefined();
    });

    const callsBefore = global.fetch.mock.calls.length;
    fireEvent.click(screen.getByText("Refresh"));

    await waitFor(() => {
      expect(global.fetch.mock.calls.length).toBeGreaterThan(callsBefore);
    });
  });

  it("cleans up interval on unmount", async () => {
    const clearIntervalSpy = vi.spyOn(global, "clearInterval");
    global.fetch = makeFetch();

    const { default: Analytics } = await import("../pages/Analytics");
    const result = render(
      <MemoryRouter>
        <Analytics />
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(global.fetch).toHaveBeenCalled();
    });

    result.unmount();

    expect(clearIntervalSpy).toHaveBeenCalled();
    clearIntervalSpy.mockRestore();
  });

  it("renders with empty events time_series", async () => {
    await renderComponent({
      events: { time_series: [] },
    });

    await waitFor(() => {
      const bar = screen.getByTestId("bar-chart");
      const data = JSON.parse(bar.textContent);
      expect(data.labels).toHaveLength(0);
    });
  });

  it("renders events chart datasets for selected sources only", async () => {
    await renderComponent();

    await waitFor(() => {
      const bar = screen.getByTestId("bar-chart");
      const data = JSON.parse(bar.textContent);
      expect(data.datasets.length).toBe(3);
      const labels = data.datasets.map((ds) => ds.label);
      expect(labels).toContain("ATM Application");
      expect(labels).toContain("Hardware Sensor");
      expect(labels).toContain("Terminal Handler");
    });
  });

  it("normalises metric name with underscores and slashes", async () => {
    await renderComponent({
      metrics: {
        time_series: [
          {
            bucket_start: "2024-01-15T10:00:00Z",
            metrics: { OS: { cpu_utilisation: 75, os_health_check: 90 } },
          },
        ],
      },
      metricsList: { metrics: ["cpu_utilisation", "os_health_check", "other_metric"] },
    });

    await waitFor(() => {
      const badges = screen.getAllByText(/ x$/);
      const texts = badges.map((b) => b.textContent);
      // "cpu_utilisation" -> "CPU Utilisation" (CPU is an acronym)
      expect(texts.some((t) => t.includes("CPU Utilisation"))).toBe(true);
      // "os_health_check" -> "OS Health Check" (OS is an acronym)
      expect(texts.some((t) => t.includes("OS Health Check"))).toBe(true);
    });
  });

  it("handles missing source colors gracefully in chart data", async () => {
    await renderComponent({
      events: {
        time_series: [
          {
            bucket_start: "2024-01-15T10:00:00Z",
            sources: { ATM_APP: 10, UNKNOWN_SOURCE: 5 },
          },
        ],
      },
    });

    await waitFor(() => {
      const bar = screen.getByTestId("bar-chart");
      const data = JSON.parse(bar.textContent);
      expect(data.datasets.length).toBe(3);
    });
  });

  it("shows Metric Types count from available metrics", async () => {
    await renderComponent({
      metricsList: { metrics: ["cpu", "mem", "disk", "net"] },
    });

    await waitFor(() => {
      expect(screen.getByText("4")).toBeDefined();
      expect(screen.getByText("Available for monitoring")).toBeDefined();
    });
  });

  it("defaults selected metrics to first 3 from list", async () => {
    await renderComponent({
      metricsList: { metrics: ["metric_a", "metric_b", "metric_c", "metric_d"] },
    });

    await waitFor(() => {
      const badges = screen.getAllByText(/ x$/);
      expect(badges.length).toBe(3);
    });
  });

  it("renders doughnut chart with colour array for anomaly types", async () => {
    await renderComponent();

    await waitFor(() => {
      const doughnut = screen.getByTestId("doughnut-chart");
      const data = JSON.parse(doughnut.textContent);
      expect(data.datasets[0].backgroundColor.length).toBe(3);
    });
  });

  it("formats normalised anomaly type names in doughnut labels", async () => {
    await renderComponent();

    await waitFor(() => {
      const doughnut = screen.getByTestId("doughnut-chart");
      const data = JSON.parse(doughnut.textContent);
      // normaliseMetricName("A1") -> "A1" (no separator, not an acronym)
      expect(data.labels).toContain("A1");
    });
  });

  it("handles large number formatting for metric counts", async () => {
    await renderComponent({
      realtime: {
        events_by_source: { ATM_APP: 2500000, HARDWARE: 1000000, TERMINAL_HANDLER: 500 },
        anomaly_types: { A1: 1000000 },
        unique_atms: 50,
      },
    });

    await waitFor(() => {
      // 2.5M + 1.0M + 0.5K = 3.5M
      const items = screen.getAllByText("3.5M");
      expect(items.length).toBeGreaterThanOrEqual(1);
      // Anomaly total: 1000000 -> "1.0M"
      const mItems = screen.getAllByText("1.0M");
      expect(mItems.length).toBeGreaterThanOrEqual(1);
    });
  });
});
