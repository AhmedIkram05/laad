import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import UncertaintyBadge from "../../components/UncertaintyBadge";

describe("UncertaintyBadge", () => {
  it("renders high confidence with green indicator and check icon", () => {
    render(<UncertaintyBadge level="high" score={0.92} />);
    expect(screen.getByText("High Confidence")).toBeDefined();
    expect(screen.getByText("92%")).toBeDefined();
    expect(screen.getByText("✓")).toBeDefined();
    expect(screen.getByText("High Confidence").style.color).toBe("rgb(16, 185, 129)");
  });

  it("renders medium confidence with amber indicator and warning icon", () => {
    render(<UncertaintyBadge level="medium" score={0.55} />);
    expect(screen.getByText("Medium Confidence")).toBeDefined();
    expect(screen.getByText("55%")).toBeDefined();
    expect(screen.getByText("⚠")).toBeDefined();
    expect(screen.getByText("Medium Confidence").style.color).toBe("rgb(245, 158, 11)");
  });

  it("renders low confidence with red indicator and cross icon", () => {
    render(<UncertaintyBadge level="low" score={0.2} />);
    expect(screen.getByText("Low Confidence")).toBeDefined();
    expect(screen.getByText("20%")).toBeDefined();
    expect(screen.getByText("✗")).toBeDefined();
    expect(screen.getByText("Low Confidence").style.color).toBe("rgb(239, 68, 68)");
  });

  it("falls back to gray and ? icon for unknown level", () => {
    render(<UncertaintyBadge level="uncertain" score={0.5} />);
    expect(screen.getByText("Uncertain Confidence")).toBeDefined();
    expect(screen.getByText("50%")).toBeDefined();
    expect(screen.getByText("?")).toBeDefined();
    expect(screen.getByText("Uncertain Confidence").style.color).toBe("rgb(107, 114, 128)");
  });

  it("rounds fractional scores to whole percent", () => {
    render(<UncertaintyBadge level="high" score={0.855} />);
    expect(screen.getByText("86%")).toBeDefined();
  });
});
