import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { useRAG } from "../providers/useRAG";
import { RAGContext } from "../providers/RAGProvider";

describe("useRAG", () => {
  it("throws error when used outside RAGProvider", () => {
    expect(() => useRAG()).toThrow();
  });

  it("returns context when used within RAGProvider", () => {
    function TestComp() {
      const ctx = useRAG();
      return <div data-testid="ctx">{typeof ctx.submitQuery}</div>;
    }

    render(
      <RAGContext.Provider value={{ messages: [], submitQuery: () => {}, handleNewChat: () => {}, input: "", setInput: () => {}, loading: false, setLoading: () => {}, activeTab: "chat", setActiveTab: () => {}, setMessages: () => {} }}>
        <TestComp />
      </RAGContext.Provider>
    );

    expect(screen.getByTestId("ctx").textContent).toBe("function");
  });
});
