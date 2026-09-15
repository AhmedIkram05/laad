import { describe, it, expect, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import SourceList from "../../components/SourceList";

const makeSource = (overrides = {}) => ({
  chunk_id: "chunk-1",
  atm_id: "ATM-GB-0001",
  timestamp: "2026-06-24T12:00:00Z",
  confidence_score: 0.9,
  text: "Error log line",
  ...overrides,
});

describe("SourceList", () => {
  beforeEach(() => {
    document.body.innerHTML = "";
  });

  it("returns null for null sources", () => {
    const { container } = render(<SourceList sources={null} />);
    expect(container.firstChild).toBeNull();
  });

  it("returns null for undefined sources", () => {
    const { container } = render(<SourceList sources={undefined} />);
    expect(container.firstChild).toBeNull();
  });

  it("returns null for empty sources", () => {
    const { container } = render(<SourceList sources={[]} />);
    expect(container.firstChild).toBeNull();
  });

  it("renders header with count and single source", () => {
    render(<SourceList sources={[makeSource()]} />);
    expect(screen.getByText("Retrieved Context")).toBeDefined();
    expect(screen.getByText("1 sources")).toBeDefined();
    expect(screen.getByText("ATM-GB-0001")).toBeDefined();
    expect(screen.getByText("90% match")).toBeDefined();
    expect(screen.queryByText("Expand All")).toBeNull();
  });

  it("toggles single item expand/collapse", () => {
    render(<SourceList sources={[makeSource()]} />);
    const btn = screen.getByText("ATM-GB-0001").closest("button");
    expect(btn.getAttribute("aria-expanded")).toBe("false");
    fireEvent.click(btn);
    expect(btn.getAttribute("aria-expanded")).toBe("true");
    expect(screen.getByText("▲")).toBeDefined();
    fireEvent.click(btn);
    expect(btn.getAttribute("aria-expanded")).toBe("false");
    expect(screen.getByText("▼")).toBeDefined();
  });

  it("shows Expand All only for multiple sources and toggles all", () => {
    render(
      <SourceList
        sources={[makeSource({ chunk_id: "a" }), makeSource({ chunk_id: "b", atm_id: "ATM-GB-0002" })]}
      />
    );
    expect(screen.getByText("2 sources")).toBeDefined();
    const toggleAll = screen.getByText("Expand All");
    fireEvent.click(toggleAll);
    expect(screen.getByText("Collapse All")).toBeDefined();
    expect(screen.getAllByText("▲")).toHaveLength(2);
    fireEvent.click(screen.getByText("Collapse All"));
    expect(screen.getByText("Expand All")).toBeDefined();
    expect(screen.getAllByText("▼")).toHaveLength(2);
  });

  it("falls back to Unknown Entity when atm_id missing", () => {
    render(<SourceList sources={[makeSource({ atm_id: undefined })]} />);
    expect(screen.getByText("Unknown Entity")).toBeDefined();
  });

  it("omits timestamp element when timestamp missing", () => {
    const { container } = render(<SourceList sources={[makeSource({ timestamp: undefined })]} />);
    expect(container.querySelector(".source-time")).toBeNull();
  });

  it("uses amber color for medium confidence and red for low", () => {
    const { rerender } = render(<SourceList sources={[makeSource({ confidence_score: 0.6 })]} />);
    expect(screen.getByText("60% match").style.color).toBe("rgb(245, 158, 11)");
    rerender(<SourceList sources={[makeSource({ confidence_score: 0.2 })]} />);
    expect(screen.getByText("20% match").style.color).toBe("rgb(239, 68, 68)");
  });

  it("uses index as key fallback when chunk_id missing", () => {
    render(<SourceList sources={[makeSource({ chunk_id: undefined })]} />);
    expect(screen.getByText("Error log line")).toBeDefined();
  });
});
