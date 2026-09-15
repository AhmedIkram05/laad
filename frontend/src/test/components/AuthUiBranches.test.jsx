import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { MemoryRouter, Routes, Route } from "react-router-dom";
import { AuthContext } from "../../auth/useAuth";
import { SearchProvider } from "../../components/GlobalSearch";
import SearchBar from "../../components/SearchBar";
import { Sidebar } from "../../components/Sidebar";
import { useRAG } from "../../providers/useRAG";

vi.mock("sonner", () => ({
  toast: { error: vi.fn(), success: vi.fn() },
}));

describe("auth UI finish-offs", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  async function renderLogin(authValue = { login: vi.fn() }, entries = ["/login"]) {
    const { default: Login } = await import("../../pages/Login");
    return render(
      <AuthContext.Provider value={authValue}>
        <MemoryRouter initialEntries={entries}>
          <Routes>
            <Route path="/login" element={<Login />} />
            <Route path="/signup" element={<div>signup stub</div>} />
            <Route path="/dashboard" element={<div>dashboard stub</div>} />
          </Routes>
        </MemoryRouter>
      </AuthContext.Provider>
    );
  }

  it("shows error toast on invalid credentials", async () => {
    const { toast } = await import("sonner");
    global.fetch = vi.fn().mockResolvedValue({ ok: false, status: 401 });
    await renderLogin();
    fireEvent.change(screen.getByLabelText("Username"), { target: { value: "u" } });
    fireEvent.change(screen.getByLabelText("Password"), { target: { value: "p" } });
    fireEvent.click(screen.getAllByText("Sign In").pop());
    await waitFor(() => {
      expect(toast.error).toHaveBeenCalledWith("Login failed. Please check your credentials.");
    });
  });

  it("shows error toast on network failure", async () => {
    const { toast } = await import("sonner");
    global.fetch = vi.fn().mockRejectedValue(new Error("down"));
    await renderLogin();
    fireEvent.change(screen.getByLabelText("Username"), { target: { value: "u" } });
    fireEvent.change(screen.getByLabelText("Password"), { target: { value: "p" } });
    fireEvent.click(screen.getAllByText("Sign In").pop());
    await waitFor(() => {
      expect(toast.error).toHaveBeenCalledWith("Login failed. Please check your credentials.");
    });
  });

  it("shows registered banner with ?registered=1", async () => {
    await renderLogin({ login: vi.fn() }, ["/login?registered=1"]);
    expect(screen.getByText("Account created successfully. Please log in.")).toBeDefined();
  });

  it("navigates to signup on footer click", async () => {
    await renderLogin();
    fireEvent.click(screen.getByText("Don't have an account? Sign up"));
    await waitFor(() => {
      expect(screen.getByText("signup stub")).toBeDefined();
    });
  });

  it("shows spinner while signing in", async () => {
    global.fetch = vi.fn().mockImplementation(() => new Promise(() => {}));
    await renderLogin();
    fireEvent.change(screen.getByLabelText("Username"), { target: { value: "u" } });
    fireEvent.change(screen.getByLabelText("Password"), { target: { value: "p" } });
    fireEvent.click(screen.getAllByText("Sign In").pop());
    await waitFor(() => {
      expect(screen.getByText("Signing in...")).toBeDefined();
    });
  });
});

describe("Sidebar finish-offs", () => {
  beforeEach(() => vi.clearAllMocks());

  function renderSidebar(initial = "/dashboard", auth = { user: { role: "admin" }, logout: vi.fn() }) {
    return render(
      <AuthContext.Provider value={auth}>
        <MemoryRouter initialEntries={[initial]}>
          <Sidebar collapsed={false} onToggle={vi.fn()} />
        </MemoryRouter>
      </AuthContext.Provider>
    );
  }

  it("navigates on nav click and marks active", () => {
    renderSidebar();
    fireEvent.click(screen.getByText("Analytics"));
    expect(screen.getByText("Analytics").closest("button").getAttribute("aria-current")).toBe("page");
    expect(screen.getByText("Dashboard").closest("button").getAttribute("aria-current")).toBeNull();
  });

  it("highlights admin settings when active", () => {
    renderSidebar();
    fireEvent.click(screen.getByText("Admin Settings"));
    expect(screen.getByText("Admin Settings").closest("button").className).toContain("bg-primary");
  });
});

describe("SearchBar without callback", () => {
  it("types and clears without onQueryChange", () => {
    render(
      <SearchProvider>
        <SearchBar />
      </SearchProvider>
    );
    const input = screen.getByPlaceholderText(/Search anomalies/i);
    fireEvent.change(input, { target: { value: "abc" } });
    expect(input.value).toBe("abc");
    fireEvent.click(screen.getByLabelText("Clear search"));
    expect(input.value).toBe("");
    expect(screen.queryByLabelText("Clear search")).toBeNull();
  });
});

describe("useRAG outside provider", () => {
  it("throws inside render without provider", () => {
    const spy = vi.spyOn(console, "error").mockImplementation(() => {});
    function Bad() {
      useRAG();
      return null;
    }
    expect(() => render(<Bad />)).toThrow("useRAG must be used within a RAGProvider");
    spy.mockRestore();
  });
});
