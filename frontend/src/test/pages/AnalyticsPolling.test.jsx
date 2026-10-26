import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, act, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

vi.mock("sonner", () => ({
  toast: { error: vi.fn(), success: vi.fn() },
}));

const ENDPOINTS = [
  "/api/insights/stats/realtime",
  "/api/insights/events",
  "/api/insights/metrics?",
  "/api/insights/metrics/list",
];

function okJson(body) {
  return { ok: true, json: () => Promise.resolve(body) };
}

async function renderAnalytics() {
  const { default: Analytics } = await import("../../pages/Analytics");
  return render(
    <MemoryRouter>
      <Analytics />
    </MemoryRouter>
  );
}

describe("Analytics polling hardening (#16)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  it("skips an interval tick while the previous cycle is still in flight", async () => {
    vi.useFakeTimers();
    // Every fetch hangs → the first cycle never finishes.
    globalThis.fetch = vi.fn().mockImplementation(() => new Promise(() => {}));

    await renderAnalytics();
    expect(globalThis.fetch).toHaveBeenCalledTimes(ENDPOINTS.length);

    // Two 5s ticks arrive while the cycle is in flight — neither may pile up
    // new requests (pre-fix: 4 requests per tick, unbounded).
    await act(async () => {
      vi.advanceTimersByTime(5000);
      vi.advanceTimersByTime(5000);
    });

    expect(globalThis.fetch).toHaveBeenCalledTimes(ENDPOINTS.length);
  });

  it("toasts at most once per outage, not once per tick", async () => {
    vi.useFakeTimers();
    globalThis.fetch = vi.fn().mockRejectedValue(new Error("Network down"));

    await renderAnalytics();

    const { toast } = await import("sonner");
    await act(async () => {
      await vi.advanceTimersByTimeAsync(5000);
      await vi.advanceTimersByTimeAsync(5000);
      await vi.advanceTimersByTimeAsync(5000);
    });

    expect(toast.error).toHaveBeenCalledTimes(1);
  });

  it("stops the realtime spinner when only the realtime endpoint fails", async () => {
    globalThis.fetch = vi.fn().mockImplementation((url) => {
      const u = String(url);
      if (u.includes("/api/insights/stats/realtime")) {
        return Promise.resolve({ ok: false, status: 500 });
      }
      if (u.includes("/api/insights/metrics/list")) {
        return Promise.resolve(okJson({ metrics: [] }));
      }
      return Promise.resolve(okJson({ time_series: [] }));
    });

    await renderAnalytics();

    // Realtime failed but the card must not spin forever: with loading=false
    // and empty stats the distribution card shows its empty message.
    await waitFor(() => {
      expect(screen.getByText("No anomalies detected in this period")).toBeDefined();
    });
  });
});
