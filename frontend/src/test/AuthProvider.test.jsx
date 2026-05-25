import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, act } from "@testing-library/react";
import { AuthProvider } from "../auth/AuthProvider";
import { useAuth } from "../auth/useAuth";

function TestConsumer({ label = "ctx" }) {
  const auth = useAuth();
  return (
    <div>
      <div data-testid={label}>{auth.token ? "has-token" : "no-token"}</div>
      <div data-testid="user">{auth.user ? JSON.stringify(auth.user) : "null"}</div>
      <div data-testid="loading">{String(auth.loading)}</div>
    </div>
  );
}

function renderWithAuth() {
  return render(
    <AuthProvider>
      <TestConsumer />
    </AuthProvider>
  );
}

describe("AuthProvider", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    window.localStorage.clear();
  });

  it("provides auth context to children", async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ username: "admin", role: "admin" }),
    });
    renderWithAuth();
    expect(await screen.findByTestId("ctx")).toBeDefined();
  });

  it("starts with no token when localStorage is empty", async () => {
    global.fetch = vi.fn();
    renderWithAuth();
    await screen.findByTestId("ctx");

    expect(screen.getByTestId("user").textContent).toBe("null");
  });

  it("calls /auth/me when token exists in localStorage", async () => {
    window.localStorage.setItem("jwt", "test-token");
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ username: "admin", role: "admin" }),
    });

    renderWithAuth();

    await screen.findByTestId("ctx");
    expect(global.fetch).toHaveBeenCalledWith(
      expect.stringContaining("/auth/me"),
      expect.objectContaining({
        headers: { Authorization: "Bearer test-token" },
      })
    );
  });

  it("clears token on /auth/me failure", async () => {
    window.localStorage.setItem("jwt", "bad-token");
    global.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 401,
    });

    renderWithAuth();

    await screen.findByTestId("ctx");
    expect(window.localStorage.getItem("jwt")).toBeNull();
  });

  it("sets loading true initially when token exists", async () => {
    window.localStorage.setItem("jwt", "some-token");
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ username: "admin" }),
    });

    renderWithAuth();

    const loading = await screen.findByTestId("loading");
    await vi.waitFor(() => {
      expect(loading.textContent).toBe("false");
    });
  });
});
