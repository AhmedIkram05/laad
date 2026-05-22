import { describe, it, expect } from "vitest";
import { render } from "@testing-library/react";

describe("Toaster", () => {
  it("renders without crashing", async () => {
    const { Toaster } = await import("../../components/ui/toast");
    const { container } = render(<Toaster />);
    expect(container.firstChild).toBeDefined();
  });
});
