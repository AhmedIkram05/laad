import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { Button } from "../../components/ui/button";

describe("Button", () => {
  it("renders as button element by default", () => {
    render(<Button>Click me</Button>);
    const btn = screen.getByText("Click me");
    expect(btn.tagName).toBe("BUTTON");
  });

  it("renders with default variant and size", () => {
    render(<Button>Default</Button>);
    const btn = screen.getByText("Default");
    expect(btn.className).toContain("bg-primary");
  });

  it("renders with destructive variant", () => {
    render(<Button variant="destructive">Delete</Button>);
    const btn = screen.getByText("Delete");
    expect(btn.className).toContain("bg-destructive");
  });

  it("renders with outline variant", () => {
    render(<Button variant="outline">Outline</Button>);
    const btn = screen.getByText("Outline");
    expect(btn.className).toContain("border");
  });

  it("renders with ghost variant", () => {
    render(<Button variant="ghost">Ghost</Button>);
    const btn = screen.getByText("Ghost");
    expect(btn.className).toContain("hover:bg-accent");
  });

  it("renders with link variant", () => {
    render(<Button variant="link">Link</Button>);
    const btn = screen.getByText("Link");
    expect(btn.className).toContain("underline-offset-4");
  });

  it("renders with different sizes", () => {
    const { rerender } = render(<Button size="sm">Small</Button>);
    expect(screen.getByText("Small").className).toContain("h-8");

    rerender(<Button size="lg">Large</Button>);
    expect(screen.getByText("Large").className).toContain("h-10");
  });

  it("applies custom className", () => {
    render(<Button className="custom-btn">Custom</Button>);
    expect(screen.getByText("Custom").className).toContain("custom-btn");
  });
});
