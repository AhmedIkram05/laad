import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

describe("Analytics", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders analytics page title", async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({}),
    });

    const { default: Analytics } = await import("../pages/Analytics");
    render(
      <MemoryRouter>
        <Analytics />
      </MemoryRouter>
    );

    const title = await screen.findByText("Analytics");
    expect(title).toBeDefined();
  });
});
