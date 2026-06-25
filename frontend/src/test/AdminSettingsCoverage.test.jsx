import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { AuthContext } from "../auth/useAuth";

vi.mock("sonner", () => ({
  toast: { error: vi.fn(), success: vi.fn() },
}));

describe("AdminSettings - extended coverage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  const authValue = {
    user: { role: "admin" },
    token: "test-token",
    login: vi.fn(),
    logout: vi.fn(),
    loading: false,
  };

  function mockFetch(handler) {
    global.fetch = vi.fn().mockImplementation((url, opts = {}) => {
      return handler(url, opts);
    });
  }

  function defaultFetchHandler(overrides = {}) {
    return (url, opts = {}) => {
      if (url.includes("/api/admin/retention") && !url.includes("cleanup") && (!opts.method || opts.method === "GET")) {
        return Promise.resolve({
          ok: true,
          json: () =>
            Promise.resolve({
              retention_days: overrides.retention_days ?? 7,
              updated_at: overrides.updated_at ?? null,
            }),
        });
      }
      if (url.includes("/api/admin/ingestion-errors")) {
        return Promise.resolve({
          ok: true,
          json: () =>
            Promise.resolve({
              data: overrides.errors ?? [],
              total: overrides.total ?? 0,
            }),
        });
      }
      return Promise.resolve({ ok: true, json: () => Promise.resolve({}) });
    };
  }

  async function renderPage() {
    const { default: AdminSettings } = await import("../pages/AdminSettings");
    return render(
      <AuthContext.Provider value={authValue}>
        <MemoryRouter>
          <AdminSettings />
        </MemoryRouter>
      </AuthContext.Provider>
    );
  }

  // ─── saveRetention ──────────────────────────────────────

  it("saveRetention shows success toast on success", async () => {
    const { toast } = await import("sonner");
    let putCalled = false;

    mockFetch((url, opts) => {
      if (url.includes("/api/admin/retention") && opts.method === "PUT") {
        putCalled = true;
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({}),
        });
      }
      return defaultFetchHandler()(url, opts);
    });

    await renderPage();
    const saveBtn = await screen.findByText("Save");
    fireEvent.click(saveBtn);

    await waitFor(() => {
      expect(putCalled).toBe(true);
      expect(toast.success).toHaveBeenCalledWith("Retention settings saved");
    });
  });

  it("saveRetention shows error toast on server error", async () => {
    const { toast } = await import("sonner");

    mockFetch((url, opts) => {
      if (url.includes("/api/admin/retention") && opts.method === "PUT") {
        return Promise.resolve({
          ok: false,
          json: () => Promise.resolve({ detail: "Invalid days value" }),
        });
      }
      return defaultFetchHandler()(url, opts);
    });

    await renderPage();
    const saveBtn = await screen.findByText("Save");
    fireEvent.click(saveBtn);

    await waitFor(() => {
      expect(toast.error).toHaveBeenCalledWith("Invalid days value");
    });
  });

  it("saveRetention shows error toast on fetch failure", async () => {
    const { toast } = await import("sonner");

    mockFetch((url, opts) => {
      if (url.includes("/api/admin/retention") && opts.method === "PUT") {
        return Promise.reject(new Error("Network error"));
      }
      return defaultFetchHandler()(url, opts);
    });

    await renderPage();
    const saveBtn = await screen.findByText("Save");
    fireEvent.click(saveBtn);

    await waitFor(() => {
      expect(toast.error).toHaveBeenCalledWith("Could not reach server");
    });
  });

  it("saveRetention shows default error when no detail field", async () => {
    const { toast } = await import("sonner");

    mockFetch((url, opts) => {
      if (url.includes("/api/admin/retention") && opts.method === "PUT") {
        return Promise.resolve({
          ok: false,
          json: () => Promise.resolve({}),
        });
      }
      return defaultFetchHandler()(url, opts);
    });

    await renderPage();
    fireEvent.click(await screen.findByText("Save"));

    await waitFor(() => {
      expect(toast.error).toHaveBeenCalledWith("Failed to save retention");
    });
  });

  // ─── runRetentionCleanup ────────────────────────────────

  it("runRetentionCleanup calls API on confirm", async () => {
    const { toast } = await import("sonner");
    let cleanupCalled = false;
    vi.spyOn(window, "confirm").mockReturnValue(true);

    mockFetch((url, opts) => {
      if (url.includes("/api/admin/cleanup/run")) {
        cleanupCalled = true;
        return Promise.resolve({
          ok: true,
          json: () =>
            Promise.resolve({
              cutoff: "2025-01-01T00:00:00",
              deleted: { logs: 100, anomalies: 5 },
            }),
        });
      }
      return defaultFetchHandler()(url, opts);
    });

    await renderPage();
    fireEvent.click(await screen.findByText("Run Cleanup"));

    await waitFor(() => {
      expect(cleanupCalled).toBe(true);
      expect(toast.success).toHaveBeenCalled();
      expect(screen.getByText("Retention cleanup complete")).toBeDefined();
    });
  });

  it("runRetentionCleanup does nothing when confirm is cancelled", async () => {
    let cleanupCalled = false;
    vi.spyOn(window, "confirm").mockReturnValue(false);

    mockFetch((url, opts) => {
      if (url.includes("/api/admin/cleanup/run")) {
        cleanupCalled = true;
      }
      return defaultFetchHandler()(url, opts);
    });

    await renderPage();
    fireEvent.click(await screen.findByText("Run Cleanup"));

    await waitFor(() => {
      expect(cleanupCalled).toBe(false);
    });
  });

  it("runRetentionCleanup shows error on failure", async () => {
    const { toast } = await import("sonner");
    vi.spyOn(window, "confirm").mockReturnValue(true);

    mockFetch((url, opts) => {
      if (url.includes("/api/admin/cleanup/run")) {
        return Promise.resolve({
          ok: false,
          json: () => Promise.resolve({ detail: "Cleanup failed" }),
        });
      }
      return defaultFetchHandler()(url, opts);
    });

    await renderPage();
    fireEvent.click(await screen.findByText("Run Cleanup"));

    await waitFor(() => {
      expect(toast.error).toHaveBeenCalledWith("Cleanup failed");
    });
  });

  it("runRetentionCleanup shows error toast on network error", async () => {
    const { toast } = await import("sonner");
    vi.spyOn(window, "confirm").mockReturnValue(true);

    mockFetch((url, opts) => {
      if (url.includes("/api/admin/cleanup/run")) {
        return Promise.reject(new Error("fail"));
      }
      return defaultFetchHandler()(url, opts);
    });

    await renderPage();
    fireEvent.click(await screen.findByText("Run Cleanup"));

    await waitFor(() => {
      expect(toast.error).toHaveBeenCalledWith("Could not reach server");
    });
  });

  it("runRetentionCleanup shows default error when no detail", async () => {
    const { toast } = await import("sonner");
    vi.spyOn(window, "confirm").mockReturnValue(true);

    mockFetch((url, opts) => {
      if (url.includes("/api/admin/cleanup/run")) {
        return Promise.resolve({
          ok: false,
          json: () => Promise.resolve({}),
        });
      }
      return defaultFetchHandler()(url, opts);
    });

    await renderPage();
    fireEvent.click(await screen.findByText("Run Cleanup"));

    await waitFor(() => {
      expect(toast.error).toHaveBeenCalledWith("Cleanup failed");
    });
  });

  // ─── runWipe ────────────────────────────────────────────

  it("runWipe calls wipe API on confirm and shows result", async () => {
    const { toast } = await import("sonner");
    let wipeCalled = false;
    vi.spyOn(window, "confirm").mockReturnValue(true);

    mockFetch((url, opts) => {
      if (url.includes("/api/admin/cleanup/wipe")) {
        wipeCalled = true;
        return Promise.resolve({
          ok: true,
          json: () =>
            Promise.resolve({
              deleted: { logs: 500, anomalies: 20 },
            }),
        });
      }
      return defaultFetchHandler()(url, opts);
    });

    await renderPage();
    fireEvent.click(await screen.findByText("Wipe All"));

    await waitFor(() => {
      expect(wipeCalled).toBe(true);
      expect(toast.success).toHaveBeenCalledWith("Data wipe complete");
      expect(screen.getByText("Full wipe complete")).toBeDefined();
    });
  });

  it("runWipe does nothing when confirm is cancelled", async () => {
    let wipeCalled = false;
    vi.spyOn(window, "confirm").mockReturnValue(false);

    mockFetch((url, opts) => {
      if (url.includes("/api/admin/cleanup/wipe")) {
        wipeCalled = true;
      }
      return defaultFetchHandler()(url, opts);
    });

    await renderPage();
    fireEvent.click(await screen.findByText("Wipe All"));

    await waitFor(() => {
      expect(wipeCalled).toBe(false);
    });
  });

  it("runWipe shows error on server error", async () => {
    const { toast } = await import("sonner");
    vi.spyOn(window, "confirm").mockReturnValue(true);

    mockFetch((url, opts) => {
      if (url.includes("/api/admin/cleanup/wipe")) {
        return Promise.resolve({
          ok: false,
          json: () => Promise.resolve({ detail: "Wipe failed" }),
        });
      }
      return defaultFetchHandler()(url, opts);
    });

    await renderPage();
    fireEvent.click(await screen.findByText("Wipe All"));

    await waitFor(() => {
      expect(toast.error).toHaveBeenCalledWith("Wipe failed");
    });
  });

  it("runWipe shows error toast on network failure", async () => {
    const { toast } = await import("sonner");
    vi.spyOn(window, "confirm").mockReturnValue(true);

    mockFetch((url, opts) => {
      if (url.includes("/api/admin/cleanup/wipe")) {
        return Promise.reject(new Error("fail"));
      }
      return defaultFetchHandler()(url, opts);
    });

    await renderPage();
    fireEvent.click(await screen.findByText("Wipe All"));

    await waitFor(() => {
      expect(toast.error).toHaveBeenCalledWith("Could not reach server");
    });
  });

  it("runWipe shows default error when no detail", async () => {
    const { toast } = await import("sonner");
    vi.spyOn(window, "confirm").mockReturnValue(true);

    mockFetch((url, opts) => {
      if (url.includes("/api/admin/cleanup/wipe")) {
        return Promise.resolve({
          ok: false,
          json: () => Promise.resolve({}),
        });
      }
      return defaultFetchHandler()(url, opts);
    });

    await renderPage();
    fireEvent.click(await screen.findByText("Wipe All"));

    await waitFor(() => {
      expect(toast.error).toHaveBeenCalledWith("Wipe failed");
    });
  });

  // ─── handleCreate ───────────────────────────────────────

  it("handleCreate shows error for empty username", async () => {
    const { toast } = await import("sonner");

    mockFetch(defaultFetchHandler());

    await renderPage();
    await screen.findByText("Create User");

    fireEvent.click(screen.getByText("Create User"));

    await waitFor(() => {
      expect(toast.error).toHaveBeenCalledWith("Username and password required");
    });
  });

  function fillCreateForm(container, username, pass, confirmPass) {
    const usernameInput = container.querySelector('input');
    const passwordInputs = container.querySelectorAll('input[type="password"]');
    fireEvent.change(usernameInput, { target: { value: username } });
    fireEvent.change(passwordInputs[0], { target: { value: pass } });
    fireEvent.change(passwordInputs[1], { target: { value: confirmPass } });
  }

  it("handleCreate shows error for password mismatch", async () => {
    const { toast } = await import("sonner");

    mockFetch(defaultFetchHandler());

    const { container } = await renderPage();
    await screen.findByText("Create User");

    fillCreateForm(container, "newuser", "pass1", "pass2");

    fireEvent.click(screen.getByText("Create User"));

    await waitFor(() => {
      expect(toast.error).toHaveBeenCalledWith("Passwords do not match");
    });
  });

  it("handleCreate calls POST and shows success on valid input", async () => {
    const { toast } = await import("sonner");
    let postCalled = false;

    mockFetch((url, opts) => {
      if (url.includes("/api/admin/users") && opts.method === "POST") {
        postCalled = true;
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ username: "newuser", role: "user" }),
        });
      }
      return defaultFetchHandler()(url, opts);
    });

    const { container } = await renderPage();
    await screen.findByText("Create User");

    fillCreateForm(container, "newuser", "pass123", "pass123");

    fireEvent.click(screen.getByText("Create User"));

    await waitFor(() => {
      expect(postCalled).toBe(true);
      expect(toast.success).toHaveBeenCalledWith("User created successfully");
      expect(screen.getByText(/Created user newuser/)).toBeDefined();
    });
  });

  it("handleCreate shows server error toast", async () => {
    const { toast } = await import("sonner");

    mockFetch((url, opts) => {
      if (url.includes("/api/admin/users") && opts.method === "POST") {
        return Promise.resolve({
          ok: false,
          json: () => Promise.resolve({ detail: "Username taken" }),
        });
      }
      return defaultFetchHandler()(url, opts);
    });

    const { container } = await renderPage();
    await screen.findByText("Create User");

    fillCreateForm(container, "newuser", "pass123", "pass123");

    fireEvent.click(screen.getByText("Create User"));

    await waitFor(() => {
      expect(toast.error).toHaveBeenCalledWith("Username taken");
    });
  });

  it("handleCreate shows default error when no detail", async () => {
    const { toast } = await import("sonner");

    mockFetch((url, opts) => {
      if (url.includes("/api/admin/users") && opts.method === "POST") {
        return Promise.resolve({
          ok: false,
          json: () => Promise.resolve({}),
        });
      }
      return defaultFetchHandler()(url, opts);
    });

    const { container } = await renderPage();
    await screen.findByText("Create User");

    fillCreateForm(container, "newuser", "pass123", "pass123");

    fireEvent.click(screen.getByText("Create User"));

    await waitFor(() => {
      expect(toast.error).toHaveBeenCalledWith("Create failed");
    });
  });

  it("handleCreate shows error toast on network failure", async () => {
    const { toast } = await import("sonner");

    mockFetch((url, opts) => {
      if (url.includes("/api/admin/users") && opts.method === "POST") {
        return Promise.reject(new Error("fail"));
      }
      return defaultFetchHandler()(url, opts);
    });

    const { container } = await renderPage();
    await screen.findByText("Create User");

    fillCreateForm(container, "newuser", "pass123", "pass123");

    fireEvent.click(screen.getByText("Create User"));

    await waitFor(() => {
      expect(toast.error).toHaveBeenCalledWith("Could not reach server");
    });
  });

  // ─── clearIngestionErrors ──────────────────────────────

  it("clearIngestionErrors calls DELETE and shows success", async () => {
    const { toast } = await import("sonner");
    let deleteCalled = false;
    vi.spyOn(window, "confirm").mockReturnValue(true);

    mockFetch((url, opts) => {
      if (url.includes("/api/admin/ingestion-errors") && opts.method === "DELETE") {
        deleteCalled = true;
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ deleted: 5 }),
        });
      }
      if (url.includes("/api/admin/ingestion-errors")) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ data: [{ id: 1, source: "syslog", error_detail: "err", timestamp: "2025-01-01" }], total: 1 }),
        });
      }
      return defaultFetchHandler()(url, opts);
    });

    await renderPage();
    await screen.findByText("Clear All");
    fireEvent.click(screen.getByText("Clear All"));

    await waitFor(() => {
      expect(deleteCalled).toBe(true);
      expect(toast.success).toHaveBeenCalledWith("Cleared 5 ingestion errors");
    });
  });

  it("clearIngestionErrors does nothing when confirm cancelled", async () => {
    let deleteCalled = false;
    vi.spyOn(window, "confirm").mockReturnValue(false);

    mockFetch((url, opts) => {
      if (url.includes("/api/admin/ingestion-errors") && opts.method === "DELETE") {
        deleteCalled = true;
      }
      if (url.includes("/api/admin/ingestion-errors")) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ data: [{ id: 1, source: "syslog", error_detail: "err", timestamp: "2025-01-01" }], total: 1 }),
        });
      }
      return defaultFetchHandler()(url, opts);
    });

    await renderPage();
    await screen.findByText("Clear All");
    fireEvent.click(screen.getByText("Clear All"));

    await waitFor(() => {
      expect(deleteCalled).toBe(false);
    });
  });

  it("clearIngestionErrors shows error toast on server failure", async () => {
    const { toast } = await import("sonner");
    vi.spyOn(window, "confirm").mockReturnValue(true);

    mockFetch((url, opts) => {
      if (url.includes("/api/admin/ingestion-errors") && opts.method === "DELETE") {
        return Promise.resolve({
          ok: false,
          json: () => Promise.resolve({ detail: "Delete failed" }),
        });
      }
      if (url.includes("/api/admin/ingestion-errors")) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ data: [{ id: 1, source: "syslog", error_detail: "err", timestamp: "2025-01-01" }], total: 1 }),
        });
      }
      return defaultFetchHandler()(url, opts);
    });

    await renderPage();
    await screen.findByText("Clear All");
    fireEvent.click(screen.getByText("Clear All"));

    await waitFor(() => {
      expect(toast.error).toHaveBeenCalledWith("Delete failed");
    });
  });

  it("clearIngestionErrors shows error toast on network failure", async () => {
    const { toast } = await import("sonner");
    vi.spyOn(window, "confirm").mockReturnValue(true);

    mockFetch((url, opts) => {
      if (url.includes("/api/admin/ingestion-errors") && opts.method === "DELETE") {
        return Promise.reject(new Error("fail"));
      }
      if (url.includes("/api/admin/ingestion-errors")) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ data: [{ id: 1, source: "syslog", error_detail: "err", timestamp: "2025-01-01" }], total: 1 }),
        });
      }
      return defaultFetchHandler()(url, opts);
    });

    await renderPage();
    await screen.findByText("Clear All");
    fireEvent.click(screen.getByText("Clear All"));

    await waitFor(() => {
      expect(toast.error).toHaveBeenCalledWith("Could not reach server");
    });
  });

  it("clearIngestionErrors shows default error when no detail", async () => {
    const { toast } = await import("sonner");
    vi.spyOn(window, "confirm").mockReturnValue(true);

    mockFetch((url, opts) => {
      if (url.includes("/api/admin/ingestion-errors") && opts.method === "DELETE") {
        return Promise.resolve({
          ok: false,
          json: () => Promise.resolve({}),
        });
      }
      if (url.includes("/api/admin/ingestion-errors")) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ data: [{ id: 1, source: "syslog", error_detail: "err", timestamp: "2025-01-01" }], total: 1 }),
        });
      }
      return defaultFetchHandler()(url, opts);
    });

    await renderPage();
    await screen.findByText("Clear All");
    fireEvent.click(screen.getByText("Clear All"));

    await waitFor(() => {
      expect(toast.error).toHaveBeenCalledWith("Failed to clear errors");
    });
  });

  // ─── loadIngestionErrors & pagination ───────────────────

  it("renders ingestion errors with expand/collapse", async () => {
    const errors = [
      { id: 1, source: "syslog", error_detail: "parse failure", timestamp: "2025-01-01T12:00:00", raw_input: "bad line" },
      { id: 2, source: "snmp", error_detail: "timeout", timestamp: "2025-01-02T12:00:00" },
    ];

    mockFetch((url, opts) => {
      if (url.includes("/api/admin/ingestion-errors")) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ data: errors, total: 2 }),
        });
      }
      return defaultFetchHandler()(url, opts);
    });

    await renderPage();

    await waitFor(() => {
      expect(screen.getByText("parse failure")).toBeDefined();
      expect(screen.getByText("timeout")).toBeDefined();
    });

    // Click to expand first error - click the button (first matching text is in the button)
    const parseButtons = screen.getAllByText("parse failure");
    fireEvent.click(parseButtons[0]);

    await waitFor(() => {
      expect(screen.getByText("Raw Input:")).toBeDefined();
    });

    // Click to collapse
    const parseButtonsAfter = screen.getAllByText("parse failure");
    fireEvent.click(parseButtonsAfter[0]);

    await waitFor(() => {
      expect(screen.queryByText("Raw Input:")).toBeNull();
    });
  });

  it("shows pagination when multiple pages of errors", async () => {
    const errors = Array.from({ length: 10 }, (_, i) => ({
      id: i + 1,
      source: "syslog",
      error_detail: `error ${i + 1}`,
      timestamp: "2025-01-01T12:00:00",
    }));

    mockFetch((url, opts) => {
      if (url.includes("/api/admin/ingestion-errors")) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ data: errors, total: 25 }),
        });
      }
      return defaultFetchHandler()(url, opts);
    });

    await renderPage();

    await waitFor(() => {
      expect(screen.getByText("Page 1 of 3")).toBeDefined();
      expect(screen.getByText("Next")).toBeDefined();
      expect(screen.getByText("Last")).toBeDefined();
    });
  });

  it("pagination Next button loads next page", async () => {
    const page1Errors = Array.from({ length: 10 }, (_, i) => ({
      id: i + 1,
      source: "syslog",
      error_detail: `error ${i + 1}`,
      timestamp: "2025-01-01T12:00:00",
    }));
    const page2Errors = Array.from({ length: 10 }, (_, i) => ({
      id: i + 11,
      source: "syslog",
      error_detail: `error ${i + 11}`,
      timestamp: "2025-01-01T12:00:00",
    }));

    let callCount = 0;
    mockFetch((url, opts) => {
      if (url.includes("/api/admin/ingestion-errors")) {
        callCount++;
        if (callCount <= 2) {
          return Promise.resolve({
            ok: true,
            json: () => Promise.resolve({ data: page1Errors, total: 25 }),
          });
        }
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ data: page2Errors, total: 25 }),
        });
      }
      return defaultFetchHandler()(url, opts);
    });

    await renderPage();

    await waitFor(() => {
      expect(screen.getByText("Page 1 of 3")).toBeDefined();
    });

    fireEvent.click(screen.getByText("Next"));

    await waitFor(() => {
      expect(screen.getByText("Page 2 of 3")).toBeDefined();
    });
  });

  it("pagination First button loads first page", async () => {
    const errors = Array.from({ length: 10 }, (_, i) => ({
      id: i + 1,
      source: "syslog",
      error_detail: `error ${i + 1}`,
      timestamp: "2025-01-01T12:00:00",
    }));

    let currentOffset = 0;
    mockFetch((url, opts) => {
      if (url.includes("/api/admin/ingestion-errors")) {
        const urlObj = new URL(url, "http://localhost");
        currentOffset = parseInt(urlObj.searchParams.get("offset") || "0");
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ data: errors, total: 25 }),
        });
      }
      return defaultFetchHandler()(url, opts);
    });

    await renderPage();

    await waitFor(() => {
      expect(screen.getByText("Page 1 of 3")).toBeDefined();
    });

    // Go to next page first
    fireEvent.click(screen.getByText("Next"));
    await waitFor(() => {
      expect(screen.getByText("Page 2 of 3")).toBeDefined();
    });

    // Click First
    fireEvent.click(screen.getByText("First"));
    await waitFor(() => {
      expect(screen.getByText("Page 1 of 3")).toBeDefined();
    });
  });

  it("pagination Prev button loads previous page", async () => {
    const errors = Array.from({ length: 10 }, (_, i) => ({
      id: i + 1,
      source: "syslog",
      error_detail: `error ${i + 1}`,
      timestamp: "2025-01-01T12:00:00",
    }));

    mockFetch((url, opts) => {
      if (url.includes("/api/admin/ingestion-errors")) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ data: errors, total: 25 }),
        });
      }
      return defaultFetchHandler()(url, opts);
    });

    await renderPage();

    await waitFor(() => {
      expect(screen.getByText("Page 1 of 3")).toBeDefined();
    });

    // Go to page 2
    fireEvent.click(screen.getByText("Next"));
    await waitFor(() => {
      expect(screen.getByText("Page 2 of 3")).toBeDefined();
    });

    // Go back to page 1
    fireEvent.click(screen.getByText("Prev"));
    await waitFor(() => {
      expect(screen.getByText("Page 1 of 3")).toBeDefined();
    });
  });

  it("pagination Last button loads last page", async () => {
    const errors = Array.from({ length: 10 }, (_, i) => ({
      id: i + 1,
      source: "syslog",
      error_detail: `error ${i + 1}`,
      timestamp: "2025-01-01T12:00:00",
    }));

    mockFetch((url, opts) => {
      if (url.includes("/api/admin/ingestion-errors")) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ data: errors, total: 25 }),
        });
      }
      return defaultFetchHandler()(url, opts);
    });

    await renderPage();

    await waitFor(() => {
      expect(screen.getByText("Page 1 of 3")).toBeDefined();
    });

    fireEvent.click(screen.getByText("Last"));

    await waitFor(() => {
      expect(screen.getByText("Page 3 of 3")).toBeDefined();
    });
  });

  it("Next/Prev/Last disabled on first/last pages respectively", async () => {
    const errors = Array.from({ length: 10 }, (_, i) => ({
      id: i + 1,
      source: "syslog",
      error_detail: `error ${i + 1}`,
      timestamp: "2025-01-01T12:00:00",
    }));

    mockFetch((url, opts) => {
      if (url.includes("/api/admin/ingestion-errors")) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ data: errors, total: 25 }),
        });
      }
      return defaultFetchHandler()(url, opts);
    });

    await renderPage();

    await waitFor(() => {
      expect(screen.getByText("Page 1 of 3")).toBeDefined();
    });

    // First page: Prev and First should be disabled
    const firstBtn = screen.getByText("First");
    const prevBtn = screen.getByText("Prev");
    expect(firstBtn).toHaveProperty("disabled", true);
    expect(prevBtn).toHaveProperty("disabled", true);
  });

  // ─── error detail with object raw_input ─────────────────

  it("renders error detail with JSON raw_input", async () => {
    const errors = [
      {
        id: 1,
        source: "syslog",
        error_detail: "parse failure",
        timestamp: "2025-01-01T12:00:00",
        raw_input: { key: "value", nested: { a: 1 } },
      },
    ];

    mockFetch((url, opts) => {
      if (url.includes("/api/admin/ingestion-errors")) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ data: errors, total: 1 }),
        });
      }
      return defaultFetchHandler()(url, opts);
    });

    await renderPage();

    await waitFor(() => {
      expect(screen.getByText("parse failure")).toBeDefined();
    });

    fireEvent.click(screen.getByText("parse failure"));

    await waitFor(() => {
      expect(screen.getByText("Raw Input:")).toBeDefined();
    });
  });

  // ─── error detail without raw_input ────────────────────

  it("renders error detail without raw input section when raw_input is missing", async () => {
    const errors = [
      {
        id: 1,
        source: "syslog",
        error_detail: "some error",
        timestamp: "2025-01-01T12:00:00",
      },
    ];

    mockFetch((url, opts) => {
      if (url.includes("/api/admin/ingestion-errors")) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ data: errors, total: 1 }),
        });
      }
      return defaultFetchHandler()(url, opts);
    });

    await renderPage();

    await waitFor(() => {
      expect(screen.getByText("some error")).toBeDefined();
    });

    fireEvent.click(screen.getByText("some error"));

    await waitFor(() => {
      expect(screen.getByText("Error Detail:")).toBeDefined();
      expect(screen.queryByText("Raw Input:")).toBeNull();
    });
  });

  // ─── fetch failure console.error ────────────────────────

  it("console.error called when retention fetch fails", async () => {
    const consoleSpy = vi.spyOn(console, "error").mockImplementation(() => {});

    mockFetch((url, opts) => {
      if (url.includes("/api/admin/retention")) {
        return Promise.reject(new Error("Network error"));
      }
      if (url.includes("/api/admin/ingestion-errors")) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ data: [], total: 0 }),
        });
      }
      return Promise.resolve({ ok: true, json: () => Promise.resolve({}) });
    });

    await renderPage();

    await waitFor(() => {
      expect(consoleSpy).toHaveBeenCalled();
    });

    consoleSpy.mockRestore();
  });

  it("console.error called when ingestion errors fetch fails", async () => {
    const consoleSpy = vi.spyOn(console, "error").mockImplementation(() => {});

    mockFetch((url, opts) => {
      if (url.includes("/api/admin/ingestion-errors")) {
        return Promise.reject(new Error("Network error"));
      }
      return defaultFetchHandler()(url, opts);
    });

    await renderPage();

    await waitFor(() => {
      expect(consoleSpy).toHaveBeenCalled();
    });

    consoleSpy.mockRestore();
  });

  // ─── retention updated_at display ──────────────────────

  it("displays retention updated_at when provided", async () => {
    mockFetch((url, opts) => {
      if (url.includes("/api/admin/retention")) {
        return Promise.resolve({
          ok: true,
          json: () =>
            Promise.resolve({ retention_days: 7, updated_at: "2025-06-15T10:30:00" }),
        });
      }
      return defaultFetchHandler()(url, opts);
    });

    await renderPage();

    await waitFor(() => {
      expect(screen.getByText(/Last updated:/)).toBeDefined();
    });
  });

  // ─── retention cleanup result display ──────────────────

  it("displays retention cleanup result with cutoff and deleted counts", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(true);

    mockFetch((url, opts) => {
      if (url.includes("/api/admin/cleanup/run")) {
        return Promise.resolve({
          ok: true,
          json: () =>
            Promise.resolve({
              cutoff: "2025-01-01T00:00:00",
              deleted: { logs: 100, anomalies: 10 },
            }),
        });
      }
      return defaultFetchHandler()(url, opts);
    });

    await renderPage();
    fireEvent.click(await screen.findByText("Run Cleanup"));

    await waitFor(() => {
      expect(screen.getByText("Retention cleanup complete")).toBeDefined();
      expect(screen.getByText(/Cutoff:/)).toBeDefined();
    });
  });

  // ─── wipe result with deleted data ─────────────────────

  it("displays wipe result with deleted counts", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(true);

    mockFetch((url, opts) => {
      if (url.includes("/api/admin/cleanup/wipe")) {
        return Promise.resolve({
          ok: true,
          json: () =>
            Promise.resolve({ deleted: { logs: 500, anomalies: 25 } }),
        });
      }
      return defaultFetchHandler()(url, opts);
    });

    await renderPage();
    fireEvent.click(await screen.findByText("Wipe All"));

    await waitFor(() => {
      expect(screen.getByText("Full wipe complete")).toBeDefined();
    });
  });

  // ─── total errors count display ────────────────────────

  it("displays total errors count", async () => {
    mockFetch((url, opts) => {
      if (url.includes("/api/admin/ingestion-errors")) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ data: [], total: 42 }),
        });
      }
      return defaultFetchHandler()(url, opts);
    });

    await renderPage();

    await waitFor(() => {
      expect(screen.getByText("42 total errors")).toBeDefined();
    });
  });

  // ─── Refresh button ────────────────────────────────────

  it("Refresh button reloads ingestion errors", async () => {
    let fetchCount = 0;
    mockFetch((url, opts) => {
      if (url.includes("/api/admin/ingestion-errors")) {
        fetchCount++;
        return Promise.resolve({
          ok: true,
          json: () =>
            Promise.resolve({ data: [], total: 0 }),
        });
      }
      return defaultFetchHandler()(url, opts);
    });

    await renderPage();

    await waitFor(() => {
      expect(screen.getByText("Refresh")).toBeDefined();
    });

    const initialCount = fetchCount;
    fireEvent.click(screen.getByText("Refresh"));

    await waitFor(() => {
      expect(fetchCount).toBeGreaterThan(initialCount);
    });
  });
});
