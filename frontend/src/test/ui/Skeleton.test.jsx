import { describe, it, expect } from "vitest";
import { render } from "@testing-library/react";
import { Skeleton } from "../../components/ui/skeleton";

describe("Skeleton", () => {
  it("renders with base classes", () => {
    const { container } = render(<Skeleton />);
    expect(container.firstChild.className).toContain("animate-pulse");
    expect(container.firstChild.className).toContain("rounded-md");
  });

  it("applies custom className", () => {
    const { container } = render(<Skeleton className="h-10 w-full" />);
    expect(container.firstChild.className).toContain("h-10");
    expect(container.firstChild.className).toContain("w-full");
  });
});
