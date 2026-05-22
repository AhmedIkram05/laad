import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

describe("Signup", () => {
  beforeEach(() => {
    vi.resetModules();
  });

  async function renderSignup() {
    const { default: Signup } = await import("../pages/Signup");
    return render(
      <MemoryRouter>
        <Signup />
      </MemoryRouter>
    );
  }

  it("renders registration form", async () => {
    await renderSignup();
    expect(screen.getByText("Create an account")).toBeDefined();
    expect(screen.getByText("Username")).toBeDefined();
    expect(screen.getByText("Password")).toBeDefined();
    expect(screen.getByText("Confirm Password")).toBeDefined();
  });

  it("shows password length error inline", async () => {
    await renderSignup();

    const pwInput = screen.getByLabelText("Password");
    fireEvent.change(pwInput, { target: { value: "short" } });

    const confirmInput = screen.getByLabelText("Confirm Password");
    fireEvent.change(confirmInput, { target: { value: "short" } });

    expect(screen.getByText("Must be at least 8 characters")).toBeDefined();
  });

  it("shows password mismatch error inline", async () => {
    await renderSignup();

    const pwInput = screen.getByLabelText("Password");
    fireEvent.change(pwInput, { target: { value: "password123" } });

    const confirmInput = screen.getByLabelText("Confirm Password");
    fireEvent.change(confirmInput, { target: { value: "different" } });

    expect(screen.getByText("Passwords do not match")).toBeDefined();
  });

  it("submits form on valid input", async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({}),
    });
    await renderSignup();

    fireEvent.change(screen.getByLabelText("Username"), { target: { value: "newuser" } });
    fireEvent.change(screen.getByLabelText("Password"), { target: { value: "password123" } });
    fireEvent.change(screen.getByLabelText("Confirm Password"), { target: { value: "password123" } });
    fireEvent.click(screen.getByText("Create Account"));
  });
});
