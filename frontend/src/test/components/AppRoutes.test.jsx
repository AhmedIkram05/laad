import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import App from "../../App";

function mockFetchForApp() {
  global.fetch = vi.fn().mockImplementation((url) => {
    if (String(url).includes("/auth/me")) {
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve({ username: "admin", role: "admin" }),
      });
    }
    if (String(url).includes("/api/anomalies")) {
      return Promise.resolve({ ok: true, json: () => Promise.resolve({ data: [] }) });
    }
    if (String(url).includes("/api/analytics/entities")) {
      return Promise.resolve({ ok: true, json: () => Promise.resolve({ entities: [] }) });
    }
    if (String(url).includes("/api/insights")) {
      return Promise.resolve({ ok: true, json: () => Promise.resolve({}) });
    }
    if (String(url).includes("/api/admin")) {
      return Promise.resolve({ ok: true, json: () => Promise.resolve({ retention_days: 7, data: [], total: 0 }) });
    }
    if (String(url).includes("/api/rag")) {
      return Promise.resolve({ ok: true, json: () => Promise.resolve({ history: [] }) });
    }
    return Promise.resolve({ ok: true, json: () => Promise.resolve({}) });
  });
}

describe("App routes", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    window.localStorage.clear();
    mockFetchForApp();
  });

  it("renders login route", async () => {
    window.history.pushState({}, "", "/login");
    render(<App />);
    await waitFor(() => {
      expect(screen.getByText("Welcome back")).toBeDefined();
    }, { timeout: 5000 });
  });

  it("renders signup route", async () => {
    window.history.pushState({}, "", "/signup");
    render(<App />);
    await waitFor(() => {
      expect(screen.getByText("Create an account")).toBeDefined();
    }, { timeout: 5000 });
  });

  it("redirects root to dashboard for authenticated user", async () => {
    window.localStorage.setItem("jwt", "test-token");
    window.history.pushState({}, "", "/");
    render(<App />);
    await waitFor(() => {
      expect(global.fetch).toHaveBeenCalledWith(
        expect.stringContaining("/auth/me"),
        expect.anything()
      );
    }, { timeout: 5000 });
  });

  it("redirects unauthenticated dashboard access to login", async () => {
    global.fetch = vi.fn().mockImplementation((url) => {
      if (String(url).includes("/auth/me")) {
        return Promise.resolve({ ok: false, status: 401 });
      }
      return Promise.resolve({ ok: true, json: () => Promise.resolve({}) });
    });
    window.history.pushState({}, "", "/dashboard");
    render(<App />);
    await waitFor(() => {
      expect(screen.getByText("Welcome back")).toBeDefined();
    }, { timeout: 5000 });
  });
});
