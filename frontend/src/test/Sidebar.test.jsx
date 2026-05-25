import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { AuthContext } from "../auth/useAuth";
import { Sidebar } from "../components/Sidebar";

function renderSidebar(authValue, collapsed = false, onToggle = vi.fn()) {
  return render(
    <AuthContext.Provider value={authValue}>
      <MemoryRouter initialEntries={["/dashboard"]}>
        <Sidebar collapsed={collapsed} onToggle={onToggle} />
      </MemoryRouter>
    </AuthContext.Provider>
  );
}

describe("Sidebar", () => {
  beforeEach(() => vi.clearAllMocks());

  it("renders navigation items", () => {
    renderSidebar({ user: { role: "user" }, logout: vi.fn() });
    expect(screen.getByText("Dashboard")).toBeDefined();
    expect(screen.getByText("Analytics")).toBeDefined();
    expect(screen.getByText("Diagnostic")).toBeDefined();
    expect(screen.getByText("Starred")).toBeDefined();
    expect(screen.getByText("Completed")).toBeDefined();
  });

  it("shows admin settings for admin users", () => {
    renderSidebar({ user: { role: "admin" }, logout: vi.fn() });
    expect(screen.getByText("Admin Settings")).toBeDefined();
  });

  it("hides admin settings for non-admin users", () => {
    renderSidebar({ user: { role: "user" }, logout: vi.fn() });
    expect(screen.queryByText("Admin Settings")).toBeNull();
  });

  it("shows Log Out button", () => {
    const logout = vi.fn();
    renderSidebar({ user: { role: "user" }, logout });
    expect(screen.getByText("Log Out")).toBeDefined();
  });

  it("calls logout and navigates on logout click", () => {
    const logout = vi.fn();
    renderSidebar({ user: { role: "user" }, logout });
    fireEvent.click(screen.getByText("Log Out"));
    expect(logout).toHaveBeenCalled();
  });

  it("renders collapsed state (icons only)", () => {
    renderSidebar({ user: { role: "user" }, logout: vi.fn() }, true);
    expect(screen.queryByText("Dashboard")).toBeNull();
    expect(screen.getByLabelText("Expand sidebar")).toBeDefined();
  });

  it("renders expanded state", () => {
    renderSidebar({ user: { role: "user" }, logout: vi.fn() }, false);
    expect(screen.getByText("Dashboard")).toBeDefined();
    expect(screen.getByLabelText("Collapse sidebar")).toBeDefined();
  });

  it("calls onToggle on collapse button click", () => {
    const onToggle = vi.fn();
    renderSidebar({ user: { role: "user" }, logout: vi.fn() }, false, onToggle);
    fireEvent.click(screen.getByLabelText("Collapse sidebar"));
    expect(onToggle).toHaveBeenCalled();
  });
});
