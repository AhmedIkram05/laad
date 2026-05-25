import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { Pagination, PaginationContent, PaginationItem, PaginationLink } from "../../components/ui/pagination";

describe("Pagination", () => {
  it("renders with items", () => {
    render(
      <Pagination>
        <PaginationContent>
          <PaginationItem>
            <PaginationLink>1</PaginationLink>
          </PaginationItem>
        </PaginationContent>
      </Pagination>
    );
    expect(screen.getByText("1")).toBeDefined();
  });
});
