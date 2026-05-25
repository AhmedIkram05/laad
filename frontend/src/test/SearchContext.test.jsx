import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { SearchProvider } from "../components/GlobalSearch";
import { useGlobalSearch } from "../components/SearchContext";

function TestComp() {
  const { query, setQuery } = useGlobalSearch();
  return (
    <div>
      <span data-testid="query">{query}</span>
      <button onClick={() => setQuery("updated")}>Update</button>
    </div>
  );
}

describe("SearchContext", () => {
  it("useGlobalSearch throws outside provider", () => {
    expect(() => render(<TestComp />)).toThrow("useGlobalSearch must be used within SearchProvider");
  });

  it("SearchProvider provides empty query by default", () => {
    render(
      <SearchProvider>
        <TestComp />
      </SearchProvider>
    );
    expect(screen.getByTestId("query").textContent).toBe("");
    fireEvent.click(screen.getByText("Update"));
    expect(screen.getByTestId("query").textContent).toBe("updated");
  });
});
