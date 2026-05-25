import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

describe("Login", () => {
  beforeEach(() => {
    vi.resetModules();
    vi.restoreAllMocks();
  });

  async function renderLogin(authValue = { login: vi.fn() }) {
    const { AuthContext } = await import("../auth/useAuth");
    const { default: Login } = await import("../pages/Login");
    return render(
      <AuthContext.Provider value={authValue}>
        <MemoryRouter>
          <Login />
        </MemoryRouter>
      </AuthContext.Provider>
    );
  }

  it("renders login form", async () => {
    await renderLogin();
    expect(screen.getByText("Welcome back")).toBeDefined();
  });

  it("has username and password fields", async () => {
    await renderLogin();
    expect(screen.getByLabelText("Username")).toBeDefined();
    expect(screen.getByLabelText("Password")).toBeDefined();
  });

  it("has sign in button", async () => {
    await renderLogin();
    expect(screen.getByText("Sign In")).toBeDefined();
  });

  it("has link to signup page", async () => {
    await renderLogin();
    expect(screen.getByText("Don't have an account? Sign up")).toBeDefined();
  });

  it("submits form to /auth/login", async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ access_token: "test-token" }),
    });
    const loginMock = vi.fn();
    await renderLogin({ login: loginMock });

    fireEvent.change(screen.getByLabelText("Username"), { target: { value: "admin" } });
    fireEvent.change(screen.getByLabelText("Password"), { target: { value: "admin123" } });
    const buttons = screen.getAllByText("Sign In");
    fireEvent.click(buttons[buttons.length - 1]);

    await waitFor(() => {
      expect(global.fetch).toHaveBeenCalledWith(
        "/auth/login",
        expect.objectContaining({ method: "POST" })
      );
    });
  });
});
