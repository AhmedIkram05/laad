export function getSystemTheme(): "light" | "dark" {
  if (typeof window === "undefined") return "light";
  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

export function getStoredTheme(): "light" | "dark" | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem("theme") as "light" | "dark" | null;
}

export function setStoredTheme(theme: "light" | "dark"): void {
  localStorage.setItem("theme", theme);
  document.documentElement.classList.toggle("dark", theme === "dark");
}

export function initializeTheme(): "light" | "dark" {
  const stored = getStoredTheme();
  if (stored) {
    document.documentElement.classList.toggle("dark", stored === "dark");
    return stored;
  }
  const system = getSystemTheme();
  document.documentElement.classList.toggle("dark", system === "dark");
  return system;
}
