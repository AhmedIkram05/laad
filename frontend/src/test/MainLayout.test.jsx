import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { AuthContext } from "../auth/useAuth";

vi.mock("../components/Sidebar", () => ({
  Sidebar: ({ collapsed }) => <div data-testid="sidebar">Sidebar {String(collapsed)}</div>,
}));

describe("MainLayout", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    window.localStorage.clear();
  });

  it("renders sidebar and providers", async () => {
    window.localStorage.setItem("sidebar-collapsed", "false");

    const { default: MainLayout } = await import("../layouts/MainLayout");
    render(
      <AuthContext.Provider value={{ user: { role: "admin" }, logout: vi.fn() }}>
        <MemoryRouter initialEntries={["/dashboard"]}>
          <MainLayout />
        </MemoryRouter>
      </AuthContext.Provider>
    );

    expect(screen.getByTestId("sidebar")).toBeDefined();
  });
});
