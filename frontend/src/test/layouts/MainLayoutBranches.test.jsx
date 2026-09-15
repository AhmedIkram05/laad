import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { AuthContext } from "../../auth/useAuth";

vi.mock("../../components/Sidebar", () => ({
  Sidebar: ({ collapsed, onToggle }) => (
    <div data-testid="sidebar">
      <span>{String(collapsed)}</span>
      <button aria-label="toggle" onClick={onToggle}>toggle</button>
    </div>
  ),
}));

describe("MainLayout branches", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.resetModules();
    window.localStorage.clear();
  });

  async function renderLayout(initialRoute = "/dashboard") {
    const { default: MainLayout } = await import("../../layouts/MainLayout");
    return render(
      <AuthContext.Provider value={{ user: { role: "user" }, logout: vi.fn() }}>
        <MemoryRouter initialEntries={[initialRoute]}>
          <MainLayout />
        </MemoryRouter>
      </AuthContext.Provider>
    );
  }

  it("starts collapsed when localStorage says true", async () => {
    window.localStorage.setItem("sidebar-collapsed", "true");
    await renderLayout();
    expect(screen.getByTestId("sidebar").textContent).toContain("true");
  });

  it("toggles collapsed and persists to localStorage", async () => {
    window.localStorage.setItem("sidebar-collapsed", "false");
    await renderLayout();
    expect(screen.getByTestId("sidebar").textContent).toContain("false");
    fireEvent.click(screen.getByText("toggle"));
    expect(screen.getByTestId("sidebar").textContent).toContain("true");
    expect(window.localStorage.getItem("sidebar-collapsed")).toBe("true");
    const main = document.querySelector("main");
    expect(main.className).toContain("ml-16");
  });

  it("applies expanded margin when not collapsed", async () => {
    window.localStorage.setItem("sidebar-collapsed", "false");
    await renderLayout();
    expect(document.querySelector("main").className).toContain("ml-60");
  });
});
