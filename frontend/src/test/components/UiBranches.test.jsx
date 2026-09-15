import { describe, it, expect } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { Button } from "../../components/ui/button";
import {
  Pagination,
  PaginationContent,
  PaginationItem,
  PaginationLink,
  PaginationPrevious,
  PaginationNext,
} from "../../components/ui/pagination";
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectLabel,
  SelectSeparator,
  SelectTrigger,
  SelectValue,
} from "../../components/ui/select";

describe("ui finish-offs", () => {
  it("button renders secondary variant and icon size", () => {
    const { rerender } = render(<Button variant="secondary">Sec</Button>);
    expect(screen.getByText("Sec").className).toContain("bg-secondary");
    rerender(<Button size="icon" aria-label="icon-btn">X</Button>);
    expect(screen.getByLabelText("icon-btn").className).toContain("w-9");
  });

  it("button renders asChild via Slot", () => {
    render(
      <Button asChild>
        <a href="/somewhere">Go</a>
      </Button>
    );
    const link = screen.getByText("Go");
    expect(link.tagName).toBe("A");
    expect(link.className).toContain("bg-primary");
  });

  it("button forwards disabled and click", () => {
    let clicks = 0;
    render(
      <Button disabled onClick={() => { clicks += 1; }}>
        Nope
      </Button>
    );
    expect(screen.getByText("Nope").closest("button").disabled).toBe(true);
  });

  it("pagination renders previous/next with labels", () => {
    render(
      <Pagination>
        <PaginationContent>
          <PaginationItem>
            <PaginationPrevious href="#" />
          </PaginationItem>
          <PaginationItem>
            <PaginationNext href="#" />
          </PaginationItem>
        </PaginationContent>
      </Pagination>
    );
    expect(screen.getByLabelText("Go to previous page")).toBeDefined();
    expect(screen.getByLabelText("Go to next page")).toBeDefined();
    expect(screen.getByText("Previous")).toBeDefined();
    expect(screen.getByText("Next")).toBeDefined();
  });

  it("pagination link marks active page", () => {
    render(
      <Pagination className="custom">
        <PaginationContent>
          <PaginationItem>
            <PaginationLink isActive href="#">2</PaginationLink>
          </PaginationItem>
        </PaginationContent>
      </Pagination>
    );
    expect(screen.getByText("2").getAttribute("aria-current")).toBe("page");
  });

  it("select label, group and separator render", () => {
    render(
      <Select open>
        <SelectGroup>
          <SelectLabel>Group label</SelectLabel>
        </SelectGroup>
        <SelectSeparator />
      </Select>
    );
    expect(screen.getByText("Group label")).toBeDefined();
  });

  it("select opens and shows items with label and separator", () => {
    render(
      <Select>
        <SelectTrigger aria-label="pick">
          <SelectValue placeholder="Pick one" />
        </SelectTrigger>
        <SelectContent>
          <SelectGroup>
            <SelectLabel>Group label</SelectLabel>
            <SelectItem value="a">Alpha</SelectItem>
          </SelectGroup>
          <SelectSeparator />
          <SelectItem value="b">Beta</SelectItem>
        </SelectContent>
      </Select>
    );
    fireEvent.click(screen.getByLabelText("pick"));
    expect(screen.getByText("Alpha")).toBeDefined();
    expect(screen.getByText("Beta")).toBeDefined();
  });
});
