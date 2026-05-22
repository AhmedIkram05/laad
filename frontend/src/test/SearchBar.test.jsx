import { describe, it, expect, vi, beforeEach } from "vitest";
import { SearchProvider } from "../components/GlobalSearch";
import { render, screen, fireEvent } from "@testing-library/react";
import SearchBar from "../components/SearchBar";

describe("SearchBar", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  function renderSearchBar(onQueryChange) {
    return render(
      <SearchProvider>
        <SearchBar onQueryChange={onQueryChange} />
      </SearchProvider>
    );
  }

  it("renders search input", () => {
    renderSearchBar();
    const input = screen.getByPlaceholderText(/Search anomalies/i);
    expect(input).toBeDefined();
  });

  it("calls onQueryChange when typing", () => {
    const onChange = vi.fn();
    renderSearchBar(onChange);
    const input = screen.getByPlaceholderText(/Search anomalies/i);
    fireEvent.change(input, { target: { value: "error" } });
    expect(onChange).toHaveBeenCalledWith("error");
  });

  it("shows clear button when query exists", () => {
    renderSearchBar();
    const input = screen.getByPlaceholderText(/Search anomalies/i);
    fireEvent.change(input, { target: { value: "test" } });
    const clearBtn = screen.getByLabelText("Clear search");
    expect(clearBtn).toBeDefined();
  });

  it("clears query on clear button click", () => {
    const onChange = vi.fn();
    renderSearchBar(onChange);
    const input = screen.getByPlaceholderText(/Search anomalies/i);
    fireEvent.change(input, { target: { value: "test" } });
    fireEvent.click(screen.getByLabelText("Clear search"));
    expect(onChange).toHaveBeenCalledWith("");
  });
});
