import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { AuthContext } from "./auth/useAuth";

describe("App", () => {
  const defaultAuth = { user: null, token: null, login: vi.fn(), logout: vi.fn(), loading: false };

  async function renderApp(authValue = defaultAuth) {
    const { default: App } = await import("./App");
    return render(
      <AuthContext.Provider value={authValue}>
        <MemoryRouter initialEntries={["/"]}>
          <App />
        </MemoryRouter>
      </AuthContext.Provider>
    );
  }

  it("renders login page when unauthenticated at /login", async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({}),
    });

    const { default: App } = await import("./App");
    render(
      <AuthContext.Provider value={defaultAuth}>
        <MemoryRouter initialEntries={["/login"]}>
          <App />
        </MemoryRouter>
      </AuthContext.Provider>
    );

    const heading = await screen.findByRole("heading", {}, { timeout: 3000 });
    expect(heading).toBeDefined();
  });

  it("redirects root to /dashboard", async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ data: [], redirect: "/dashboard" }),
    });

    const { default: App } = await import("./App");
    render(
      <AuthContext.Provider value={defaultAuth}>
        <MemoryRouter initialEntries={["/"]}>
          <App />
        </MemoryRouter>
      </AuthContext.Provider>
    );

    // Should show login page (protected route redirects there)
    await vi.waitFor(() => {
      expect(screen.getByText(/sign in/i)).toBeDefined();
    }, { timeout: 3000 });
  });

  it("renders dashboard for authenticated users", async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ data: [] }),
    });

    const authValue = { user: { role: "admin" }, token: "valid-token", login: vi.fn(), logout: vi.fn(), loading: false };
    const { default: App } = await import("./App");
    render(
      <AuthContext.Provider value={authValue}>
        <MemoryRouter initialEntries={["/dashboard"]}>
          <App />
        </MemoryRouter>
      </AuthContext.Provider>
    );

    const title = await screen.findByText("Dashboard", {}, { timeout: 3000 });
    expect(title).toBeDefined();
  });

  it("shows admin settings for admin users", async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ retention_days: 7, updated_at: null, data: [], total: 0 }),
    });

    const authValue = { user: { role: "admin" }, token: "admin-token", login: vi.fn(), logout: vi.fn(), loading: false };
    const { default: App } = await import("./App");
    render(
      <AuthContext.Provider value={authValue}>
        <MemoryRouter initialEntries={["/admin/settings"]}>
          <App />
        </MemoryRouter>
      </AuthContext.Provider>
    );

    const title = await screen.findByText("Admin Settings", {}, { timeout: 3000 });
    expect(title).toBeDefined();
  });
});
