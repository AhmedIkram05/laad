import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, act, waitFor } from "@testing-library/react";
import { AuthProvider } from "../../auth/AuthProvider";
import { useAuth } from "../../auth/useAuth";

function Consumer({ onAuth }) {
  const auth = useAuth();
  if (onAuth) onAuth(auth);
  return (
    <div>
      <span data-testid="token">{auth.token ?? "none"}</span>
      <span data-testid="user">{auth.user ? auth.user.username : "null"}</span>
      <span data-testid="loading">{String(auth.loading)}</span>
      <button onClick={() => auth.login("new-jwt")}>do-login</button>
      <button onClick={() => auth.login(null)}>do-login-null</button>
      <button onClick={() => auth.logout()}>do-logout</button>
    </div>
  );
}

describe("AuthProvider actions", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    window.localStorage.clear();
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ username: "admin", role: "admin" }),
    });
  });

  it("login stores token and triggers reload", async () => {
    let captured;
    render(
      <AuthProvider>
        <Consumer onAuth={(a) => { captured = a; }} />
      </AuthProvider>
    );
    await waitFor(() => expect(screen.getByTestId("loading").textContent).toBe("false"));
    await act(async () => { captured.login("new-jwt"); });
    expect(window.localStorage.getItem("jwt")).toBe("new-jwt");
    expect(screen.getByTestId("token").textContent).toBe("new-jwt");
  });

  it("login with null does not store token", async () => {
    let captured;
    render(
      <AuthProvider>
        <Consumer onAuth={(a) => { captured = a; }} />
      </AuthProvider>
    );
    await waitFor(() => expect(screen.getByTestId("loading").textContent).toBe("false"));
    await act(async () => { captured.login(null); });
    expect(window.localStorage.getItem("jwt")).toBeNull();
    expect(screen.getByTestId("token").textContent).toBe("none");
  });

  it("logout calls API and clears state even on success", async () => {
    window.localStorage.setItem("jwt", "tok");
    global.fetch = vi.fn().mockImplementation((url) => {
      if (String(url).includes("/auth/me")) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve({ username: "u" }) });
      }
      return Promise.resolve({ ok: true, json: () => Promise.resolve({}) });
    });
    let captured;
    render(
      <AuthProvider>
        <Consumer onAuth={(a) => { captured = a; }} />
      </AuthProvider>
    );
    await waitFor(() => expect(screen.getByTestId("token").textContent).toBe("tok"));
    await act(async () => { await captured.logout(); });
    expect(window.localStorage.getItem("jwt")).toBeNull();
    expect(screen.getByTestId("token").textContent).toBe("none");
    expect(global.fetch).toHaveBeenCalledWith(
      expect.stringContaining("/auth/logout"),
      expect.objectContaining({ method: "POST" })
    );
  });

  it("logout clears state when server call fails", async () => {
    window.localStorage.setItem("jwt", "tok");
    global.fetch = vi.fn().mockImplementation((url) => {
      if (String(url).includes("/auth/me")) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve({ username: "u" }) });
      }
      return Promise.reject(new Error("down"));
    });
    let captured;
    render(
      <AuthProvider>
        <Consumer onAuth={(a) => { captured = a; }} />
      </AuthProvider>
    );
    await waitFor(() => expect(screen.getByTestId("token").textContent).toBe("tok"));
    await act(async () => { await captured.logout(); });
    expect(window.localStorage.getItem("jwt")).toBeNull();
  });

  it("handles /auth/me network throw by clearing loading", async () => {    global.fetch = vi.fn().mockRejectedValue(new Error("down"));
    const spy = vi.spyOn(console, "error").mockImplementation(() => {});
    render(
      <AuthProvider>
        <Consumer />
      </AuthProvider>
    );
    await waitFor(() => expect(screen.getByTestId("loading").textContent).toBe("false"));
    expect(screen.getByTestId("user").textContent).toBe("null");
    spy.mockRestore();
  });

  it("unmounts cleanly during /auth/me flight", async () => {
    let resolveMe;
    global.fetch = vi.fn().mockImplementation(
      () => new Promise((res) => { resolveMe = res; })
    );
    const { unmount } = render(
      <AuthProvider>
        <Consumer />
      </AuthProvider>
    );
    unmount();
    await act(async () => {
      resolveMe({ ok: true, json: () => Promise.resolve({ username: "u" }) });
    });
  });

  it("useAuth throws inside render without provider", () => {
    const spy = vi.spyOn(console, "error").mockImplementation(() => {});
    function Bad() {
      useAuth();
      return null;
    }
    expect(() => render(<Bad />)).toThrow("useAuth must be used within an AuthProvider");
    spy.mockRestore();
  });
});
