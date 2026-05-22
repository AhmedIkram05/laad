import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { Card, CardHeader, CardTitle, CardDescription, CardContent, CardFooter } from "../../components/ui/card";

describe("Card", () => {
  it("renders card with content", () => {
    render(<Card>Card content</Card>);
    expect(screen.getByText("Card content")).toBeDefined();
  });

  it("renders all subcomponents", () => {
    render(
      <Card>
        <CardHeader>
          <CardTitle>Title</CardTitle>
          <CardDescription>Description</CardDescription>
        </CardHeader>
        <CardContent>Content</CardContent>
        <CardFooter>Footer</CardFooter>
      </Card>
    );
    expect(screen.getByText("Title")).toBeDefined();
    expect(screen.getByText("Description")).toBeDefined();
    expect(screen.getByText("Content")).toBeDefined();
    expect(screen.getByText("Footer")).toBeDefined();
  });
});
