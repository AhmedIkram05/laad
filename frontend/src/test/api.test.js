import { describe, it, expect, vi, beforeEach } from "vitest";

function clearLocalStorage() {
  const keys = Object.keys(window.localStorage);
  keys.forEach((k) => window.localStorage.removeItem(k));
}

describe("API Client", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    clearLocalStorage();
  });

  describe("getAuthHeaders", () => {
    it("returns empty object when no token", async () => {
      const { getAuthHeaders } = await import("../api/api");
      expect(getAuthHeaders()).toEqual({});
    });

    it("returns Authorization header when token exists", async () => {
      window.localStorage.setItem("jwt", "test-token");
      const { getAuthHeaders } = await import("../api/api");
      const headers = getAuthHeaders();
      expect(headers).toEqual({ Authorization: "Bearer test-token" });
    });
  });

  describe("fetchAnomalies", () => {
    it("builds correct URL with default params", async () => {
      global.fetch = vi.fn().mockResolvedValue({
        ok: true,
        json: () => Promise.resolve([]),
      });
      const { fetchAnomalies } = await import("../api/api");
      await fetchAnomalies();

      const calledUrl = global.fetch.mock.calls[0][0];
      expect(calledUrl).toContain("/api/anomalies?");
      expect(calledUrl).toContain("sort_by=score");
    });

    it("includes all query params when provided", async () => {
      global.fetch = vi.fn().mockResolvedValue({
        ok: true,
        json: () => Promise.resolve([]),
      });
      window.localStorage.setItem("jwt", "t");
      const { fetchAnomalies } = await import("../api/api");
      await fetchAnomalies(1, 24, "severity", "ML_ENSEMBLE", 1, "ATM-001", "A1", "CRITICAL", "atm");

      const calledUrl = global.fetch.mock.calls[0][0];
      expect(calledUrl).toContain("is_active=1");
      expect(calledUrl).toContain("sort_by=severity");
      expect(calledUrl).toContain("detection_source=ML_ENSEMBLE");
      expect(calledUrl).toContain("atm_id=ATM-001");
    });

    it("throws on non-ok response", async () => {
      global.fetch = vi.fn().mockResolvedValue({
        ok: false,
        status: 500,
      });
      const { fetchAnomalies } = await import("../api/api");
      await expect(fetchAnomalies()).rejects.toThrow("Request failed: 500");
    });
  });

  describe("fetchEntities", () => {
    it("correct endpoint", async () => {
      global.fetch = vi.fn().mockResolvedValue({
        ok: true,
        json: () => Promise.resolve([{ id: "ATM-001" }]),
      });
      const { fetchEntities } = await import("../api/api");
      const result = await fetchEntities();
      expect(global.fetch.mock.calls[0][0]).toBe("/api/analytics/entities");
      expect(result).toEqual([{ id: "ATM-001" }]);
    });
  });

  describe("fetchDetailedAnalysis", () => {
    it("correct endpoint with type", async () => {
      global.fetch = vi.fn().mockResolvedValue({
        ok: true,
        json: () => Promise.resolve({ data: "test" }),
      });
      const { fetchDetailedAnalysis } = await import("../api/api");
      await fetchDetailedAnalysis("A1");
      expect(global.fetch.mock.calls[0][0]).toContain("/api/analysis/detailed?Anomaly=A1");
    });
  });

  describe("toggleStar", () => {
    it("sends PATCH request", async () => {
      global.fetch = vi.fn().mockResolvedValue({
        ok: true,
        json: () => Promise.resolve({}),
      });
      const { toggleStar } = await import("../api/api");
      await toggleStar(42);
      expect(global.fetch.mock.calls[0][0]).toBe("/api/anomalies/42/star");
      expect(global.fetch.mock.calls[0][1].method).toBe("PATCH");
    });
  });

  describe("toggleComplete", () => {
    it("sends PATCH request", async () => {
      global.fetch = vi.fn().mockResolvedValue({
        ok: true,
        json: () => Promise.resolve({}),
      });
      const { toggleComplete } = await import("../api/api");
      await toggleComplete(7);
      expect(global.fetch.mock.calls[0][0]).toBe("/api/anomalies/7/resolve");
      expect(global.fetch.mock.calls[0][1].method).toBe("PATCH");
    });
  });

  describe("fetchMetrics", () => {
    it("correct endpoint with params", async () => {
      global.fetch = vi.fn().mockResolvedValue({
        ok: true,
        json: () => Promise.resolve({}),
      });
      const { fetchMetrics } = await import("../api/api");
      await fetchMetrics(48, 30);
      expect(global.fetch.mock.calls[0][0]).toContain("/api/analysis/metrics?hours=48&bucket_minutes=30");
    });
  });

  describe("queryRAG", () => {
    it("sends POST with correct body", async () => {
      global.fetch = vi.fn().mockResolvedValue({
        ok: true,
        json: () => Promise.resolve({ answer: "test" }),
      });
      const { queryRAG } = await import("../api/api");
      await queryRAG("test query", "ATM-001", 5, true);

      const [url, options] = global.fetch.mock.calls[0];
      expect(url).toBe("/api/rag/query");
      expect(options.method).toBe("POST");
      const body = JSON.parse(options.body);
      expect(body.query).toBe("test query");
      expect(body.atm_id).toBe("ATM-001");
      expect(body.top_k).toBe(5);
    });
  });

  describe("submitRAGFeedback", () => {
    it("sends POST with feedback", async () => {
      global.fetch = vi.fn().mockResolvedValue({
        ok: true,
        json: () => Promise.resolve({}),
      });
      const { submitRAGFeedback } = await import("../api/api");
      await submitRAGFeedback("q123", { rating: 5 });
      const body = JSON.parse(global.fetch.mock.calls[0][1].body);
      expect(body.query_id).toBe("q123");
      expect(body.feedback.rating).toBe(5);
    });
  });

  describe("getRAGHistory", () => {
    it("correct endpoint with pagination", async () => {
      global.fetch = vi.fn().mockResolvedValue({
        ok: true,
        json: () => Promise.resolve([]),
      });
      const { getRAGHistory } = await import("../api/api");
      await getRAGHistory(10, 20);
      expect(global.fetch.mock.calls[0][0]).toContain("/api/rag/history?limit=10&offset=20");
    });
  });

  describe("getRAGStats", () => {
    it("correct endpoint", async () => {
      global.fetch = vi.fn().mockResolvedValue({
        ok: true,
        json: () => Promise.resolve({}),
      });
      const { getRAGStats } = await import("../api/api");
      await getRAGStats();
      expect(global.fetch.mock.calls[0][0]).toBe("/api/rag/stats");
    });
  });
});
