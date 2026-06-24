import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { AuthContext } from "../auth/useAuth";

describe("AdminSettings", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  const authValue = { user: { role: "admin" }, token: "t", login: vi.fn(), logout: vi.fn(), loading: false };

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

  it("renders admin page title", async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ retention_days: 7, updated_at: null, data: [], total: 0 }),
    });

    await renderPage();
    const title = await screen.findByText("Admin Settings");
    expect(title).toBeDefined();
  });

  it("renders data retention and user creation sections", async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ retention_days: 7, updated_at: null, data: [], total: 0 }),
    });

    await renderPage();
    expect(await screen.findByText("Data Retention")).toBeDefined();
    expect(await screen.findByText("Create New User")).toBeDefined();
  });

  it("shows loading state for ingestion errors", async () => {
    let resolveErrors;
    global.fetch = vi.fn().mockImplementation((url) => {
      if (url.includes("/api/admin/retention")) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ retention_days: 7, updated_at: null }),
        });
      }
      if (url.includes("/api/admin/ingestion-errors")) {
        return new Promise((resolve) => {
          resolveErrors = resolve;
        });
      }
      return Promise.resolve({ ok: true, json: () => Promise.resolve({}) });
    });

    await renderPage();
    expect(await screen.findByText("Loading...")).toBeDefined();

    resolveErrors({
      ok: true,
      json: () => Promise.resolve({ data: [], total: 0 }),
    });
  }, 5000);

  it("shows no ingestion errors state", async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ retention_days: 7, updated_at: null, data: [], total: 0 }),
    });

    await renderPage();
    expect(await screen.findByText("No ingestion errors found.")).toBeDefined();
  });

  it("has save retention button", async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ retention_days: 7, updated_at: null, data: [], total: 0 }),
    });

    await renderPage();
    expect(await screen.findByText("Save")).toBeDefined();
    expect(screen.getByText("Run Cleanup")).toBeDefined();
  });

  it("has user creation form fields", async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ retention_days: 7, updated_at: null, data: [], total: 0 }),
    });

    await renderPage();
    expect(await screen.findByText("Username")).toBeDefined();
    expect(screen.getByText("Password")).toBeDefined();
    expect(screen.getByText("Confirm Password")).toBeDefined();
    expect(screen.getByText("Role")).toBeDefined();
    expect(screen.getByText("Create User")).toBeDefined();
  });
});
