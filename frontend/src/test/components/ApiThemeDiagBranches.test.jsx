import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { AuthContext } from "../../auth/useAuth";

describe("api error branches", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    window.localStorage.clear();
  });

  it("maps 404 to no-logs message", async () => {
    global.fetch = vi.fn().mockResolvedValue({ ok: false, status: 404 });
    const { fetchAnomalies } = await import("../../api/api");
    await expect(fetchAnomalies()).rejects.toThrow("No relevant logs found");
  });

  it("maps 401 to session-expired message", async () => {
    global.fetch = vi.fn().mockResolvedValue({ ok: false, status: 401 });
    const { fetchEntities } = await import("../../api/api");
    await expect(fetchEntities()).rejects.toThrow("Session expired");
  });

  it("maps 429 to rate-limit message", async () => {
    global.fetch = vi.fn().mockResolvedValue({ ok: false, status: 429 });
    const { getRAGStats } = await import("../../api/api");
    await expect(getRAGStats()).rejects.toThrow("Too many requests");
  });

  it("maps AbortError to timeout message", async () => {
    const err = new Error("aborted");
    err.name = "AbortError";
    global.fetch = vi.fn().mockRejectedValue(err);
    const { queryRAG } = await import("../../api/api");
    await expect(queryRAG("hi")).rejects.toThrow("Request timed out");
  });

  it("rethrows non-abort network errors", async () => {
    global.fetch = vi.fn().mockRejectedValue(new Error("boom"));
    const { fetchMetrics } = await import("../../api/api");
    await expect(fetchMetrics()).rejects.toThrow("boom");
  });
});

describe("ThemeProvider media change", () => {
  let handlers;
  let removeSpy;
  let addSpy;

  beforeEach(() => {
    handlers = [];
    removeSpy = vi.fn();
    addSpy = vi.fn((_, h) => { handlers.push(h); });
    Object.defineProperty(window, "matchMedia", {
      writable: true,
      value: vi.fn().mockImplementation(() => ({
        matches: false,
        media: "",
        addEventListener: addSpy,
        removeEventListener: removeSpy,
      })),
    });
    document.documentElement.classList.remove("light", "dark");
  });

  afterEach(() => {
    document.documentElement.classList.remove("light", "dark");
  });

  it("switches theme on system change and cleans up", async () => {
    const { ThemeProvider } = await import("../../providers/ThemeProvider");
    const result = render(
      <ThemeProvider>
        <div>child</div>
      </ThemeProvider>
    );
    expect(document.documentElement.classList.contains("light")).toBe(true);
    handlers.forEach((h) => h({ matches: true }));
    await waitFor(() => {
      expect(document.documentElement.classList.contains("dark")).toBe(true);
    });
    result.unmount();
    expect(removeSpy).toHaveBeenCalled();
  });
});

describe("DiagnosticAssistant branches", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  async function renderDA(ragOverrides = {}) {
    const { RAGContext } = await import("../../providers/RAGProvider");
    const { default: DiagnosticAssistant } = await import("../../pages/DiagnosticAssistant");
    const base = {
      messages: [{ id: 0, role: "assistant", content: "Hello!" }],
      input: "",
      setInput: vi.fn(),
      loading: false,
      activeTab: "chat",
      setActiveTab: vi.fn(),
      submitQuery: vi.fn(),
      handleNewChat: vi.fn(),
      setMessages: vi.fn(),
    };
    global.fetch = vi.fn().mockResolvedValue({ ok: true, json: () => Promise.resolve({}) });
    return render(
      <AuthContext.Provider value={{ user: null, token: null, login: vi.fn(), logout: vi.fn(), loading: false }}>
        <RAGContext.Provider value={{ ...base, ...ragOverrides }}>
          <MemoryRouter>
            <DiagnosticAssistant />
          </MemoryRouter>
        </RAGContext.Provider>
      </AuthContext.Provider>
    );
  }

  it("disables Send when input is empty and input change calls setInput", async () => {
    const setInput = vi.fn();
    await renderDA({ setInput, input: "" });
    expect(screen.getByText("Send").closest("button").disabled).toBe(true);
    fireEvent.change(screen.getByPlaceholderText(/Ask about ATM/), { target: { value: "hello" } });
    expect(setInput).toHaveBeenCalledWith("hello");
  });

  it("shows typing indicator while loading", async () => {
    await renderDA({ loading: true, messages: [{ id: 0, role: "assistant", content: "Hi" }] });
    expect(document.querySelectorAll(".animate-bounce").length).toBeGreaterThanOrEqual(3);
  });

  it("hides example queries once conversation has replies", async () => {
    await renderDA({
      messages: [
        { id: 0, role: "assistant", content: "Hi" },
        { id: 1, role: "user", content: "Q" },
      ],
    });
    expect(screen.queryByText("Try asking about")).toBeNull();
  });

  it("shows history skeletons while history loads", async () => {
    global.fetch = vi.fn().mockImplementation(() => new Promise(() => {}));
    const { RAGContext } = await import("../../providers/RAGProvider");
    const { default: DiagnosticAssistant } = await import("../../pages/DiagnosticAssistant");
    render(
      <AuthContext.Provider value={{ user: null, token: null, login: vi.fn(), logout: vi.fn(), loading: false }}>
        <RAGContext.Provider value={{
          messages: [{ id: 0, role: "assistant", content: "Hi" }],
          input: "",
          setInput: vi.fn(),
          loading: false,
          activeTab: "history",
          setActiveTab: vi.fn(),
          submitQuery: vi.fn(),
          handleNewChat: vi.fn(),
          setMessages: vi.fn(),
        }}>
          <MemoryRouter>
            <DiagnosticAssistant />
          </MemoryRouter>
        </RAGContext.Provider>
      </AuthContext.Provider>
    );
    await waitFor(() => {
      expect(document.querySelectorAll(".animate-pulse").length).toBeGreaterThanOrEqual(5);
    });
  });
});

describe("AdminSettings small branches", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  async function renderAdmin(fetchImpl) {
    global.fetch = fetchImpl;
    const { default: AdminSettings } = await import("../../pages/AdminSettings");
    return render(
      <AuthContext.Provider value={{ user: { role: "admin" }, token: "t", login: vi.fn(), logout: vi.fn(), loading: false }}>
        <MemoryRouter>
          <AdminSettings />
        </MemoryRouter>
      </AuthContext.Provider>
    );
  }

  it("keeps defaults when retention fetch is not ok", async () => {
    global.fetch = vi.fn().mockImplementation((url) => {
      if (String(url).includes("/api/admin/retention")) {
        return Promise.resolve({ ok: false, status: 403, json: () => Promise.resolve({}) });
      }
      return Promise.resolve({ ok: true, json: () => Promise.resolve({ data: [], total: 0 }) });
    });
    const { default: AdminSettings } = await import("../../pages/AdminSettings");
    render(
      <AuthContext.Provider value={{ user: { role: "admin" }, token: "t", login: vi.fn(), logout: vi.fn(), loading: false }}>
        <MemoryRouter>
          <AdminSettings />
        </MemoryRouter>
      </AuthContext.Provider>
    );
    await waitFor(() => {
      expect(screen.getByText("Admin Settings")).toBeDefined();
    });
  });

  it("shows empty ingestion state when fetch is not ok", async () => {
    await renderAdmin(
      vi.fn().mockImplementation((url) => {
        if (String(url).includes("/api/admin/ingestion-errors")) {
          return Promise.resolve({ ok: false, status: 500, json: () => Promise.resolve({}) });
        }
        return Promise.resolve({ ok: true, json: () => Promise.resolve({ retention_days: 7, updated_at: null }) });
      })
    );
    await waitFor(() => {
      expect(screen.getByText("No ingestion errors found.")).toBeDefined();
    });
  });
});
