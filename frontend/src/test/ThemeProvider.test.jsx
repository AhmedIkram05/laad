import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen } from "@testing-library/react";

describe("ThemeProvider", () => {
  let matchMediaMock;

  beforeEach(() => {
    matchMediaMock = vi.fn().mockImplementation((query) => ({
      matches: query === "(prefers-color-scheme: dark)" ? false : false,
      media: query,
      addEventListener: vi.fn((_, handler) => {}),
      removeEventListener: vi.fn(),
    }));
    window.matchMedia = matchMediaMock;
  });

  afterEach(() => {
    document.documentElement.classList.remove("light", "dark");
  });

  it("renders children", async () => {
    const { ThemeProvider } = await import("../providers/ThemeProvider");
    render(
      <ThemeProvider>
        <div>test child</div>
      </ThemeProvider>
    );
    expect(screen.getByText("test child")).toBeDefined();
  });

  it("sets light class by default", async () => {
    const { ThemeProvider } = await import("../providers/ThemeProvider");
    render(
      <ThemeProvider>
        <div>child</div>
      </ThemeProvider>
    );
    expect(document.documentElement.classList.contains("light")).toBe(true);
  });

  it("sets dark class when preferred", async () => {
    matchMediaMock = vi.fn().mockImplementation((query) => ({
      matches: query === "(prefers-color-scheme: dark)" ? true : false,
      media: query,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    }));
    window.matchMedia = matchMediaMock;

    const { ThemeProvider } = await import("../providers/ThemeProvider");
    render(
      <ThemeProvider>
        <div>child</div>
      </ThemeProvider>
    );
    expect(document.documentElement.classList.contains("dark")).toBe(true);
  });
});
