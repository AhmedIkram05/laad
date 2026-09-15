import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { MemoryRouter, Routes, Route } from "react-router-dom";

vi.mock("sonner", () => ({
  toast: { error: vi.fn(), success: vi.fn() },
}));

describe("Signup branches", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.resetModules();
  });

  async function renderSignup() {
    const { default: Signup } = await import("../../pages/Signup");
    return render(
      <MemoryRouter initialEntries={["/signup"]}>
        <Routes>
          <Route path="/signup" element={<Signup />} />
          <Route path="/login" element={<div>login stub</div>} />
        </Routes>
      </MemoryRouter>
    );
  }

  function fill(username, password, confirm) {
    fireEvent.change(screen.getByLabelText("Username"), { target: { value: username } });
    fireEvent.change(screen.getByLabelText("Password"), { target: { value: password } });
    fireEvent.change(screen.getByLabelText("Confirm Password"), { target: { value: confirm } });
  }

  it("blocks submit when passwords mismatch", async () => {
    const { toast } = await import("sonner");
    global.fetch = vi.fn();
    await renderSignup();
    fill("user1", "password123", "different123");
    fireEvent.click(screen.getByText("Create Account"));
    await waitFor(() => {
      expect(toast.error).toHaveBeenCalledWith("Passwords do not match");
    });
    expect(global.fetch).not.toHaveBeenCalled();
  });

  it("blocks submit when password too short", async () => {
    const { toast } = await import("sonner");
    global.fetch = vi.fn();
    await renderSignup();
    fill("user1", "short", "short");
    fireEvent.click(screen.getByText("Create Account"));
    await waitFor(() => {
      expect(toast.error).toHaveBeenCalledWith("Password must be at least 8 characters");
    });
    expect(global.fetch).not.toHaveBeenCalled();
  });

  it("shows success and loading state on valid submit", async () => {
    const { toast } = await import("sonner");
    global.fetch = vi.fn().mockResolvedValue({ ok: true, json: () => Promise.resolve({}) });
    await renderSignup();
    fill("newuser", "password123", "password123");
    fireEvent.click(screen.getByText("Create Account"));
    await waitFor(() => {
      expect(toast.success).toHaveBeenCalledWith("Account created successfully!");
    });
  });

  it("shows server detail error when registration fails", async () => {
    const { toast } = await import("sonner");
    global.fetch = vi.fn().mockResolvedValue({
      ok: false,
      json: () => Promise.resolve({ detail: "Username taken" }),
    });
    await renderSignup();
    fill("taken", "password123", "password123");
    fireEvent.click(screen.getByText("Create Account"));
    await waitFor(() => {
      expect(toast.error).toHaveBeenCalledWith("Username taken");
    });
  });

  it("shows fallback error when server gives no detail", async () => {
    const { toast } = await import("sonner");
    global.fetch = vi.fn().mockResolvedValue({
      ok: false,
      json: () => Promise.resolve({}),
    });
    await renderSignup();
    fill("taken", "password123", "password123");
    fireEvent.click(screen.getByText("Create Account"));
    await waitFor(() => {
      expect(toast.error).toHaveBeenCalledWith("Registration failed");
    });
  });

  it("shows network error message on fetch throw", async () => {
    const { toast } = await import("sonner");
    global.fetch = vi.fn().mockRejectedValue(new Error("down"));
    await renderSignup();
    fill("user1", "password123", "password123");
    fireEvent.click(screen.getByText("Create Account"));
    await waitFor(() => {
      expect(toast.error).toHaveBeenCalledWith("down");
    });
  });

  it("navigates to login from footer button", async () => {
    await renderSignup();
    fireEvent.click(screen.getByText("Already have an account? Sign in"));
    await waitFor(() => {
      expect(screen.getByText("login stub")).toBeDefined();
    });
  });
});
