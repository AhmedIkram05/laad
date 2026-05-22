import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { Input } from "../../components/ui/input";

describe("Input", () => {
  it("renders input element", () => {
    render(<Input placeholder="Enter text" />);
    const input = screen.getByPlaceholderText("Enter text");
    expect(input.tagName).toBe("INPUT");
  });

  it("passes type prop", () => {
    render(<Input type="password" data-testid="pw" />);
    expect(screen.getByTestId("pw").type).toBe("password");
  });

  it("applies custom className", () => {
    render(<Input className="custom-input" data-testid="inp" />);
    expect(screen.getByTestId("inp").className).toContain("custom-input");
  });
});
