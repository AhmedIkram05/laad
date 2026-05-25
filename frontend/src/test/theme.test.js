import { describe, it, expect, vi, beforeEach } from "vitest";
import {
  getSystemTheme,
  getStoredTheme,
  setStoredTheme,
  initializeTheme,
} from "../lib/theme";

describe("getSystemTheme", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("returns dark when prefers-color-scheme is dark", () => {
    Object.defineProperty(window, "matchMedia", {
      writable: true,
      value: vi.fn().mockImplementation((query) => ({
        matches: true,
        media: query,
      })),
    });
    expect(getSystemTheme()).toBe("dark");
  });

  it("returns light when prefers-color-scheme is light", () => {
    Object.defineProperty(window, "matchMedia", {
      writable: true,
      value: vi.fn().mockImplementation((query) => ({
        matches: false,
        media: query,
      })),
    });
    expect(getSystemTheme()).toBe("light");
  });
});

describe("getStoredTheme", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    window.localStorage.clear();
  });

  it("returns null when no theme stored", () => {
    expect(getStoredTheme()).toBeNull();
  });

  it("returns stored theme", () => {
    window.localStorage.setItem("theme", "dark");
    expect(getStoredTheme()).toBe("dark");
  });
});

describe("setStoredTheme", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    window.localStorage.clear();
    document.documentElement.classList.remove("dark");
  });

  it("stores theme in localStorage", () => {
    setStoredTheme("dark");
    expect(window.localStorage.getItem("theme")).toBe("dark");
  });

  it("adds dark class to document for dark theme", () => {
    setStoredTheme("dark");
    expect(document.documentElement.classList.contains("dark")).toBe(true);
  });

  it("removes dark class for light theme", () => {
    document.documentElement.classList.add("dark");
    setStoredTheme("light");
    expect(document.documentElement.classList.contains("dark")).toBe(false);
  });
});

describe("initializeTheme", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    window.localStorage.clear();
    document.documentElement.classList.remove("dark");
    Object.defineProperty(window, "matchMedia", {
      writable: true,
      value: vi.fn().mockImplementation((query) => ({
        matches: false,
        media: query,
      })),
    });
  });

  it("returns stored theme when one exists", () => {
    window.localStorage.setItem("theme", "dark");
    expect(initializeTheme()).toBe("dark");
    expect(document.documentElement.classList.contains("dark")).toBe(true);
  });

  it("falls back to system theme when no stored theme", () => {
    expect(initializeTheme()).toBe("light");
  });
});
