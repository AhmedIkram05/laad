import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { Label } from "../../components/ui/label";

describe("Label", () => {
  it("renders with text", () => {
    render(<Label>Username</Label>);
    expect(screen.getByText("Username")).toBeDefined();
  });

  it("renders with htmlFor", () => {
    render(
      <>
        <Label htmlFor="test-input">Test</Label>
        <input id="test-input" />
      </>
    );
    const label = screen.getByText("Test");
    expect(label.getAttribute("for")).toBe("test-input");
  });
});
