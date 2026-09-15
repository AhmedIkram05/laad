import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, act, waitFor } from "@testing-library/react";
import { useRAG } from "../../providers/useRAG";

function Consumer({ onRag }) {
  const rag = useRAG();
  if (onRag) onRag(rag);
  return (
    <div>
      <span data-testid="count">{rag.messages.length}</span>
      <span data-testid="input">{rag.input}</span>
      <span data-testid="tab">{rag.activeTab}</span>
      <span data-testid="loading">{String(rag.loading)}</span>
    </div>
  );
}

describe("RAGProvider storage and guards", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    window.localStorage.clear();
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ answer: "hi", confidence_level: "high", uncertainty_score: 0.1, sources: [] }),
    });
  });

  it("falls back to defaults on corrupt localStorage", async () => {
    window.localStorage.setItem("rag_messages", "{bad json");
    window.localStorage.setItem("rag_input", "[oops");
    window.localStorage.setItem("rag_active_tab", "{nope");
    const { RAGProvider } = await import("../../providers/RAGProvider");
    render(
      <RAGProvider>
        <Consumer />
      </RAGProvider>
    );
    expect(screen.getByTestId("count").textContent).toBe("1");
    expect(screen.getByTestId("tab").textContent).toBe("chat");
  });

  it("ignores empty and whitespace queries", async () => {
    const { RAGProvider } = await import("../../providers/RAGProvider");
    let captured;
    render(
      <RAGProvider>
        <Consumer onRag={(r) => { captured = r; }} />
      </RAGProvider>
    );
    await act(async () => { await captured.submitQuery(""); });
    await act(async () => { await captured.submitQuery("   "); });
    expect(global.fetch).not.toHaveBeenCalled();
  });

  it("blocks concurrent submits while loading", async () => {
    let resolveFetch;
    global.fetch = vi.fn().mockImplementation(
      () => new Promise((res) => { resolveFetch = res; })
    );
    const { RAGProvider } = await import("../../providers/RAGProvider");
    let captured;
    render(
      <RAGProvider>
        <Consumer onRag={(r) => { captured = r; }} />
      </RAGProvider>
    );
    let first;
    await act(async () => { first = captured.submitQuery("q1"); });
    await act(async () => { await captured.submitQuery("q2"); });
    expect(global.fetch).toHaveBeenCalledTimes(1);
    await act(async () => {
      resolveFetch({ ok: true, json: () => Promise.resolve({ answer: "done" }) });
      await first;
    });
  });

  it("supports direct-value setMessages with 50-message trim", async () => {
    const { RAGProvider } = await import("../../providers/RAGProvider");
    let captured;
    render(
      <RAGProvider>
        <Consumer onRag={(r) => { captured = r; }} />
      </RAGProvider>
    );
    const many = Array.from({ length: 60 }, (_, i) => ({ id: i, role: "user", content: `m${i}` }));
    await act(async () => { captured.setMessages(many); });
    expect(screen.getByTestId("count").textContent).toBe("50");
  });

  it("survives localStorage write failures", async () => {
    const warnSpy = vi.spyOn(console, "warn").mockImplementation(() => {});
    const setSpy = vi.spyOn(window.localStorage, "setItem").mockImplementation(() => {
      throw new Error("disk full");
    });
    const { RAGProvider } = await import("../../providers/RAGProvider");
    let captured;
    render(
      <RAGProvider>
        <Consumer onRag={(r) => { captured = r; }} />
      </RAGProvider>
    );
    await act(async () => { captured.setInput("hello"); });
    expect(screen.getByTestId("input").textContent).toBe("hello");
    expect(warnSpy).toHaveBeenCalled();
    setSpy.mockRestore();
    warnSpy.mockRestore();
  });

  it("supports functional setInput and setActiveTab", async () => {
    const { RAGProvider } = await import("../../providers/RAGProvider");
    let captured;
    render(
      <RAGProvider>
        <Consumer onRag={(r) => { captured = r; }} />
      </RAGProvider>
    );
    await act(async () => { captured.setInput((prev) => `${prev}hi`); });
    expect(screen.getByTestId("input").textContent).toBe("hi");
    await act(async () => { captured.setActiveTab("history"); });
    expect(screen.getByTestId("tab").textContent).toBe("history");
    await act(async () => { captured.setActiveTab(() => "chat"); });
    expect(screen.getByTestId("tab").textContent).toBe("chat");
  });
});
