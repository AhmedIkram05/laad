import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, act } from "@testing-library/react";
import { useRAG } from "../providers/useRAG";

function TestConsumer() {
  const rag = useRAG();
  return (
    <div>
      <span data-testid="loading">{rag.loading ? "true" : "false"}</span>
      <span data-testid="activeTab">{rag.activeTab}</span>
      <span data-testid="msgCount">{rag.messages.length}</span>
      <button data-testid="submitQuery" onClick={() => rag.submitQuery("test query")}>Submit</button>
      <button data-testid="newChat" onClick={() => rag.handleNewChat()}>New Chat</button>
      <input data-testid="input" value={rag.input} onChange={(e) => rag.setInput(e.target.value)} />
    </div>
  );
}

describe("RAGProvider", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    window.localStorage.clear();
  });

  it("renders children and provides initial state", async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ answer: "test answer" }),
    });

    const { RAGProvider } = await import("../providers/RAGProvider");
    render(
      <RAGProvider>
        <TestConsumer />
      </RAGProvider>
    );

    expect(screen.getByTestId("loading").textContent).toBe("false");
    expect(screen.getByTestId("activeTab").textContent).toBe("chat");
    expect(parseInt(screen.getByTestId("msgCount").textContent)).toBeGreaterThan(0);
  });

  it("handleNewChat resets to initial message and tab", async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ answer: "test" }),
    });

    const { RAGProvider } = await import("../providers/RAGProvider");
    render(
      <RAGProvider>
        <TestConsumer />
      </RAGProvider>
    );

    await act(async () => {
      screen.getByTestId("newChat").click();
    });

    expect(screen.getByTestId("activeTab").textContent).toBe("chat");
    expect(parseInt(screen.getByTestId("msgCount").textContent)).toBe(1);
  });

  it("submitQuery sends message and updates state", async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({
        answer: "diagnostic response",
        confidence_level: "high",
        uncertainty_score: 0.1,
        sources: [],
      }),
    });

    const { RAGProvider } = await import("../providers/RAGProvider");
    render(
      <RAGProvider>
        <TestConsumer />
      </RAGProvider>
    );

    await act(async () => {
      screen.getByTestId("submitQuery").click();
    });

    expect(global.fetch).toHaveBeenCalled();
    const callArgs = global.fetch.mock.calls[0];
    expect(callArgs[0]).toBe("/api/rag/query");
    const body = JSON.parse(callArgs[1].body);
    expect(body.query).toBe("test query");
  });

  it("handles fetch error gracefully", async () => {
    global.fetch = vi.fn().mockRejectedValue(new Error("Network error"));
    const toastMock = { error: vi.fn() };

    vi.doMock("sonner", () => ({
      toast: toastMock,
    }));

    const { RAGProvider } = await import("../providers/RAGProvider");
    render(
      <RAGProvider>
        <TestConsumer />
      </RAGProvider>
    );

    await act(async () => {
      screen.getByTestId("submitQuery").click();
    });
  });
});
