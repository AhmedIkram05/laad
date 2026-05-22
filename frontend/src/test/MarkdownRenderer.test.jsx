import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import MarkdownRenderer from "../components/MarkdownRenderer";

describe("MarkdownRenderer", () => {
  it("returns null for empty content", () => {
    const { container } = render(<MarkdownRenderer content="" />);
    expect(container.innerHTML).toBe("");
  });

  it("returns null for null content", () => {
    const { container } = render(<MarkdownRenderer content={null} />);
    expect(container.innerHTML).toBe("");
  });

  it("renders headings", () => {
    const { container } = render(<MarkdownRenderer content={"# Heading 1\n## Heading 2"} />);
    expect(container.innerHTML).toContain("Heading 1");
    expect(container.innerHTML).toContain("Heading 2");
  });

  it("renders paragraphs", () => {
    render(<MarkdownRenderer content="This is a paragraph." />);
    expect(screen.getByText("This is a paragraph.")).toBeDefined();
  });

  it("renders bold text", () => {
    render(<MarkdownRenderer content="This is **bold** text" />);
    expect(screen.getByText("bold")).toBeDefined();
  });

  it("renders italic text", () => {
    render(<MarkdownRenderer content="This is *italic* text" />);
    expect(screen.getByText("italic")).toBeDefined();
  });

  it("renders inline code", () => {
    render(<MarkdownRenderer content="Use `code` inline" />);
    expect(screen.getByText("code")).toBeDefined();
  });

  it("renders unordered lists", () => {
    const { container } = render(<MarkdownRenderer content={"- Item 1\n- Item 2"} />);
    expect(container.querySelector("ul")).toBeDefined();
    expect(container.querySelectorAll("li").length).toBe(2);
  });

  it("renders ordered lists", () => {
    const { container } = render(<MarkdownRenderer content={"1. First\n2. Second"} />);
    expect(container.querySelector("ol")).toBeDefined();
    expect(container.querySelectorAll("li").length).toBe(2);
  });

  it("renders code blocks", () => {
    const { container } = render(<MarkdownRenderer content={"```\ncode block\n```"} />);
    expect(container.querySelector("pre")).toBeDefined();
    expect(container.querySelector("code")).toBeDefined();
  });

  it("renders highlighted text", () => {
    render(<MarkdownRenderer content="This is --highlighted-- text" />);
    expect(screen.getByText("highlighted")).toBeDefined();
  });
});
