import { createContext, useContext } from "react";

export const SearchContext = createContext(null);

export function useGlobalSearch() {
  const ctx = useContext(SearchContext);
  if (!ctx) throw new Error("useGlobalSearch must be used within SearchProvider");
  return ctx;
}
