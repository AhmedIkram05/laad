import { describe, it, expect, vi, beforeEach } from "vitest";
import { render } from "@testing-library/react";
import { MemoryRouter, Routes, Route } from "react-router-dom";

describe("AdminRoute", () => {
  beforeEach(() => {
    vi.resetModules();
  });

  async function renderAdmin(authValue) {
    const { AuthContext } = await import("../auth/useAuth");
    const { default: AdminRoute } = await import("../components/AdminRoute");
    return render(
      <AuthContext.Provider value={authValue}>
        <MemoryRouter initialEntries={["/admin"]}>
          <Routes>
            <Route element={<AdminRoute />}>
              <Route path="/admin" element={<div>Admin Content</div>} />
            </Route>
            <Route path="/login" element={<div>Login Page</div>} />
            <Route path="/dashboard" element={<div>Dashboard Page</div>} />
          </Routes>
        </MemoryRouter>
      </AuthContext.Provider>
    );
  }

  it("renders null while loading", async () => {
    const { container } = await renderAdmin({ user: null, loading: true });
    expect(container.innerHTML).toBe("");
  });

  it("redirects to /login when no user", async () => {
    const { container } = await renderAdmin({ user: null, loading: false });
    expect(container.innerHTML).toContain("Login Page");
  });

  it("redirects non-admin to /dashboard", async () => {
    const { container } = await renderAdmin({ user: { username: "user", role: "user" }, loading: false });
    expect(container.innerHTML).toContain("Dashboard Page");
  });

  it("renders Outlet for admin", async () => {
    const { container } = await renderAdmin({
      user: { username: "admin", role: "admin" },
      loading: false,
    });
    expect(container.innerHTML).toContain("Admin Content");
  });
});
