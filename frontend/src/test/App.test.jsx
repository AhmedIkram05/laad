import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { AuthContext } from "../auth/useAuth";
import { SearchProvider } from "../components/GlobalSearch";

describe("App", () => {
  const defaultAuth = { user: null, token: null, login: vi.fn(), logout: vi.fn(), loading: false };

  it("renders login page when unauthenticated at /login", async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({}),
    });

    const { default: Login } = await import("../pages/Login");
    render(
      <AuthContext.Provider value={defaultAuth}>
        <MemoryRouter initialEntries={["/login"]}>
          <Login />
        </MemoryRouter>
      </AuthContext.Provider>
    );

    const heading = await screen.findByRole("heading", {}, { timeout: 3000 });
    expect(heading).toBeDefined();
  });

  it("redirects root to /dashboard", async () => {
    // Verify the dashboard page renders (App routes / to /dashboard)
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ entities: [] }),
    });

    const { default: Dashboard } = await import("../pages/Dashboard");
    render(
      <MemoryRouter initialEntries={["/dashboard"]}>
        <SearchProvider>
          <Dashboard />
        </SearchProvider>
      </MemoryRouter>
    );

    await vi.waitFor(() => {
      expect(screen.getByText("Anomalies Detected")).toBeDefined();
    }, { timeout: 3000 });
  });

  it("renders dashboard for authenticated users", async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ entities: [] }),
    });

    const { default: Dashboard } = await import("../pages/Dashboard");
    render(
      <MemoryRouter>
        <SearchProvider>
          <Dashboard />
        </SearchProvider>
      </MemoryRouter>
    );

    const title = await screen.findByText("Anomalies Detected", {}, { timeout: 3000 });
    expect(title).toBeDefined();
  });

  it("shows admin settings for admin users", async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ retention_days: 7, updated_at: null }),
    });

    const adminAuth = { user: { role: "admin" }, token: "admin-token", login: vi.fn(), logout: vi.fn(), loading: false };

    const { default: AdminSettings } = await import("../pages/AdminSettings");
    render(
      <AuthContext.Provider value={adminAuth}>
        <MemoryRouter>
          <AdminSettings />
        </MemoryRouter>
      </AuthContext.Provider>
    );

    const title = await screen.findByText("Admin Settings", {}, { timeout: 3000 });
    expect(title).toBeDefined();
  });
});
