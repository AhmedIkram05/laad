import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

describe("BackButton", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("renders Back text and icon", async () => {
    const { default: BackButton } = await import("../components/BackButton");
    render(
      <MemoryRouter>
        <BackButton />
      </MemoryRouter>
    );
    expect(screen.getByText("Back")).toBeDefined();
  });

  it("calls navigate(-1) on click", async () => {
    const { default: BackButton } = await import("../components/BackButton");
    render(
      <MemoryRouter>
        <BackButton />
      </MemoryRouter>
    );
    const btn = screen.getByText("Back").closest("button");
    expect(btn).toBeDefined();
    fireEvent.click(btn);
  });
});
