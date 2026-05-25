import { describe, it, expect, vi, beforeEach } from "vitest";
import { render } from "@testing-library/react";
import { MemoryRouter, Routes, Route } from "react-router-dom";

describe("ProtectedRoute", () => {
  beforeEach(() => {
    vi.resetModules();
  });

  async function renderProtected(authValue) {
    const { AuthContext } = await import("../auth/useAuth");
    const { default: ProtectedRoute } = await import("../components/ProtectedRoute");
    return render(
      <AuthContext.Provider value={authValue}>
        <MemoryRouter initialEntries={["/protected"]}>
          <Routes>
            <Route element={<ProtectedRoute />}>
              <Route path="/protected" element={<div>Protected Content</div>} />
            </Route>
            <Route path="/login" element={<div>Login Page</div>} />
          </Routes>
        </MemoryRouter>
      </AuthContext.Provider>
    );
  }

  it("renders null while loading", async () => {
    const { container } = await renderProtected({ user: null, loading: true });
    expect(container.innerHTML).toBe("");
  });

  it("redirects to /login when no user", async () => {
    const { container } = await renderProtected({ user: null, loading: false });
    expect(container.innerHTML).toContain("Login Page");
  });

  it("renders Outlet when authenticated", async () => {
    const { container } = await renderProtected({
      user: { username: "test" },
      loading: false,
    });
    expect(container.innerHTML).toContain("Protected Content");
  });
});
