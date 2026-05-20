import { createContext, useContext, useEffect, useState } from "react";
import { setStoredTheme } from "../lib/theme";

const ThemeContext = createContext({ theme: "dark", setTheme: () => {} });

export function ThemeProvider({ children }) {
  const [theme, setThemeState] = useState("dark");

  const setTheme = (newTheme) => {
    setStoredTheme(newTheme);
    setThemeState(newTheme);
  };

  useEffect(() => {
    document.documentElement.classList.add("dark");
    setThemeState("dark");
  }, []);

  return (
    <ThemeContext.Provider value={{ theme, setTheme }}>
      {children}
    </ThemeContext.Provider>
  );
}

export const useTheme = () => useContext(ThemeContext);