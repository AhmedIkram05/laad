import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { AuthContext } from "../auth/useAuth";
import { RAGContext } from "../providers/RAGProvider";

vi.mock("sonner", () => ({
  toast: { error: vi.fn(), success: vi.fn() },
}));

vi.mock("../api/api", () => ({
  getRAGStats: vi.fn().mockResolvedValue({}),
  getRAGHistory: vi.fn().mockResolvedValue({ history: [] }),
  queryRAG: vi.fn(),
}));

describe("DiagnosticAssistant - extended coverage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  const mockAuthValue = {
    user: { role: "admin" },
    token: "test-token",
    login: vi.fn(),
    logout: vi.fn(),
    loading: false,
  };

  const defaultRagValue = {
    messages: [{ id: 0, role: "assistant", content: "Hello! I'm your ATM diagnostic assistant." }],
    input: "",
    setInput: vi.fn(),
    loading: false,
    activeTab: "chat",
    setActiveTab: vi.fn(),
    submitQuery: vi.fn(),
    handleNewChat: vi.fn(),
    setMessages: vi.fn(),
  };

  function mockFetch(handler) {
    global.fetch = vi.fn().mockImplementation((url, opts = {}) => {
      return handler(url, opts);
    });
  }

  async function renderComponent(ragOverrides = {}, authOverrides = {}) {
    const { default: DiagnosticAssistant } = await import("../pages/DiagnosticAssistant");
    return render(
      <AuthContext.Provider value={{ ...mockAuthValue, ...authOverrides }}>
        <RAGContext.Provider value={{ ...defaultRagValue, ...ragOverrides }}>
          <MemoryRouter>
            <DiagnosticAssistant />
          </MemoryRouter>
        </RAGContext.Provider>
      </AuthContext.Provider>
    );
  }

  // ─── getRAGStats on mount ──────────────────────────────

  it("calls getRAGStats on mount", async () => {
    const api = await import("../api/api");
    mockFetch(() =>
      Promise.resolve({ ok: true, json: () => Promise.resolve([]) })
    );

    await renderComponent();

    await waitFor(() => {
      expect(api.getRAGStats).toHaveBeenCalled();
    });
  });

  it("logs error when getRAGStats fails", async () => {
    const api = await import("../api/api");
    api.getRAGStats.mockRejectedValueOnce(new Error("stats fail"));
    const consoleSpy = vi.spyOn(console, "error").mockImplementation(() => {});

    mockFetch(() =>
      Promise.resolve({ ok: true, json: () => Promise.resolve([]) })
    );

    await renderComponent();

    await waitFor(() => {
      expect(consoleSpy).toHaveBeenCalled();
    });

    consoleSpy.mockRestore();
  });

  // ─── tab switching to history ──────────────────────────

  it("calls setActiveTab when clicking History tab", async () => {
    const setActiveTab = vi.fn();
    const { getRAGHistory } = await import("../api/api");
    getRAGHistory.mockResolvedValueOnce({ history: [] });

    mockFetch(() =>
      Promise.resolve({ ok: true, json: () => Promise.resolve([]) })
    );

    await renderComponent({ setActiveTab });

    fireEvent.click(screen.getByText("History"));

    await waitFor(() => {
      expect(setActiveTab).toHaveBeenCalledWith("history");
    });
  });

  it("calls setActiveTab when clicking Chat tab", async () => {
    const setActiveTab = vi.fn();

    mockFetch(() =>
      Promise.resolve({ ok: true, json: () => Promise.resolve([]) })
    );

    await renderComponent({
      setActiveTab,
      activeTab: "history",
    });

    fireEvent.click(screen.getByText("Chat"));

    await waitFor(() => {
      expect(setActiveTab).toHaveBeenCalledWith("chat");
    });
  });

  // ─── fetchHistory ──────────────────────────────────────

  it("fetches history when switching to history tab", async () => {
    const { getRAGHistory } = await import("../api/api");
    getRAGHistory.mockResolvedValueOnce({
      history: [
        { id: 1, query_text: "test query", answer_text: "test answer", uncertainty_score: 0.8, created_at: "2025-01-01T12:00:00" },
      ],
    });

    mockFetch(() =>
      Promise.resolve({ ok: true, json: () => Promise.resolve([]) })
    );

    await renderComponent({ activeTab: "history" });

    await waitFor(() => {
      expect(getRAGHistory).toHaveBeenCalledWith(20, 0);
    });

    expect(await screen.findByText("test query")).toBeDefined();
  });

  it("shows history items when history data exists", async () => {
    const { getRAGHistory } = await import("../api/api");
    getRAGHistory.mockResolvedValueOnce({
      history: [
        { id: 1, query_text: "What is A1?", answer_text: "Answer 1", uncertainty_score: 0.8, created_at: "2025-01-01T12:00:00" },
        { id: 2, query_text: "What is A2?", answer_text: "Answer 2", uncertainty_score: 0.3, created_at: "2025-01-02T12:00:00" },
      ],
    });

    mockFetch(() =>
      Promise.resolve({ ok: true, json: () => Promise.resolve([]) })
    );

    await renderComponent({ activeTab: "history" });

    expect(await screen.findByText("What is A1?")).toBeDefined();
    expect(screen.getByText("What is A2?")).toBeDefined();
  });

  it("logs error when getRAGHistory fails", async () => {
    const { getRAGHistory } = await import("../api/api");
    getRAGHistory.mockRejectedValueOnce(new Error("history fail"));
    const consoleSpy = vi.spyOn(console, "error").mockImplementation(() => {});

    mockFetch(() =>
      Promise.resolve({ ok: true, json: () => Promise.resolve([]) })
    );

    await renderComponent({ activeTab: "history" });

    await waitFor(() => {
      expect(consoleSpy).toHaveBeenCalled();
    });

    consoleSpy.mockRestore();
  });

  // ─── HistoryItem expand/collapse ───────────────────────

  it("HistoryItem expands and shows answer text on click", async () => {
    const { getRAGHistory } = await import("../api/api");
    getRAGHistory.mockResolvedValueOnce({
      history: [
        { id: 1, query_text: "Test query?", answer_text: "Test answer content", uncertainty_score: 0.8, created_at: "2025-01-01T12:00:00" },
      ],
    });

    mockFetch(() =>
      Promise.resolve({ ok: true, json: () => Promise.resolve([]) })
    );

    await renderComponent({ activeTab: "history" });

    const queryText = await screen.findByText("Test query?");
    fireEvent.click(queryText.closest("button"));

    await waitFor(() => {
      expect(screen.getByText("Test answer content")).toBeDefined();
    });
  });

  it("HistoryItem collapses when clicked again", async () => {
    const { getRAGHistory } = await import("../api/api");
    getRAGHistory.mockResolvedValueOnce({
      history: [
        { id: 1, query_text: "Test query?", answer_text: "Test answer content", uncertainty_score: 0.8, created_at: "2025-01-01T12:00:00" },
      ],
    });

    mockFetch(() =>
      Promise.resolve({ ok: true, json: () => Promise.resolve([]) })
    );

    await renderComponent({ activeTab: "history" });

    const button = (await screen.findByText("Test query?")).closest("button");
    fireEvent.click(button);
    await waitFor(() => {
      expect(screen.getByText("Test answer content")).toBeDefined();
    });

    fireEvent.click(button);
    await waitFor(() => {
      expect(screen.queryByText("Test answer content")).toBeNull();
    });
  });

  // ─── Load More pagination ──────────────────────────────

  it("shows Load More button when more history available", async () => {
    const { getRAGHistory } = await import("../api/api");
    const twentyItems = Array.from({ length: 20 }, (_, i) => ({
      id: i + 1,
      query_text: `Query ${i + 1}`,
      answer_text: `Answer ${i + 1}`,
      uncertainty_score: 0.5,
      created_at: "2025-01-01T12:00:00",
    }));
    getRAGHistory.mockResolvedValueOnce({ history: twentyItems });

    mockFetch(() =>
      Promise.resolve({ ok: true, json: () => Promise.resolve([]) })
    );

    await renderComponent({ activeTab: "history" });

    await waitFor(() => {
      expect(screen.getByText("Load More")).toBeDefined();
    });
  });

  it("does not show Load More when fewer than 20 items", async () => {
    const { getRAGHistory } = await import("../api/api");
    getRAGHistory.mockResolvedValueOnce({
      history: [
        { id: 1, query_text: "Q1", answer_text: "A1", uncertainty_score: 0.5, created_at: "2025-01-01T12:00:00" },
      ],
    });

    mockFetch(() =>
      Promise.resolve({ ok: true, json: () => Promise.resolve([]) })
    );

    await renderComponent({ activeTab: "history" });

    await waitFor(() => {
      expect(screen.queryByText("Load More")).toBeNull();
    });
  });

  it("Load More button fetches next page", async () => {
    const { getRAGHistory } = await import("../api/api");
    const twentyItems = Array.from({ length: 20 }, (_, i) => ({
      id: i + 1,
      query_text: `Query ${i + 1}`,
      answer_text: `Answer ${i + 1}`,
      uncertainty_score: 0.5,
      created_at: "2025-01-01T12:00:00",
    }));
    getRAGHistory
      .mockResolvedValueOnce({ history: twentyItems })
      .mockResolvedValueOnce({ history: [{ id: 21, query_text: "Q21", answer_text: "A21", uncertainty_score: 0.5, created_at: "2025-01-01T12:00:00" }] });

    mockFetch(() =>
      Promise.resolve({ ok: true, json: () => Promise.resolve([]) })
    );

    await renderComponent({ activeTab: "history" });

    await waitFor(() => {
      expect(screen.getByText("Load More")).toBeDefined();
    });

    fireEvent.click(screen.getByText("Load More"));

    await waitFor(() => {
      expect(getRAGHistory).toHaveBeenCalledWith(20, 20);
    });
  });

  // ─── handleSubmit ──────────────────────────────────────

  it("handleSubmit calls submitQuery with input text", async () => {
    const submitQuery = vi.fn();
    const setInput = vi.fn();

    mockFetch(() =>
      Promise.resolve({ ok: true, json: () => Promise.resolve([]) })
    );

    await renderComponent({ submitQuery, input: "What is A1?", setInput });

    const form = document.querySelector("form");
    fireEvent.submit(form);

    await waitFor(() => {
      expect(submitQuery).toHaveBeenCalledWith("What is A1?");
    });
  });

  // ─── example query buttons ────────────────────────────

  it("clicking example query button sets input text", async () => {
    const setInput = vi.fn();

    mockFetch(() =>
      Promise.resolve({ ok: true, json: () => Promise.resolve([]) })
    );

    await renderComponent({ setInput });

    const button = screen.getByText("What does anomaly type A1 mean?");
    fireEvent.click(button);

    await waitFor(() => {
      expect(setInput).toHaveBeenCalledWith("What does anomaly type A1 mean?");
    });
  });

  it("clicking second example query button sets input text", async () => {
    const setInput = vi.fn();

    mockFetch(() =>
      Promise.resolve({ ok: true, json: () => Promise.resolve([]) })
    );

    await renderComponent({ setInput });

    fireEvent.click(screen.getByText("How do I fix a cash cassette empty error?"));

    await waitFor(() => {
      expect(setInput).toHaveBeenCalledWith("How do I fix a cash cassette empty error?");
    });
  });

  // ─── ConfidenceBadge variants ─────────────────────────

  it("renders HIGH confidence badge for assistant message with high score", async () => {
    const messages = [
      { id: 0, role: "assistant", content: "Hello!" },
      {
        id: 1,
        role: "assistant",
        content: "Analysis result",
        uncertainty: {
          level: "HIGH",
          score: 0.9,
          selfConsistencyScore: 0.85,
          verbalizedConfidence: 0.88,
          groundingScore: 0.92,
          crossEncoderUsed: true,
          wasRevised: false,
          modelUsed: "gpt-4",
        },
      },
    ];

    mockFetch(() =>
      Promise.resolve({ ok: true, json: () => Promise.resolve([]) })
    );

    await renderComponent({ messages });

    expect(screen.getByText(/HIGH confidence/)).toBeDefined();
  });

  it("renders MEDIUM confidence badge", async () => {
    const messages = [
      { id: 0, role: "assistant", content: "Hello!" },
      {
        id: 1,
        role: "assistant",
        content: "Analysis result",
        uncertainty: {
          level: "MEDIUM",
          score: 0.6,
          selfConsistencyScore: 0.55,
          verbalizedConfidence: 0.58,
          groundingScore: 0.62,
          crossEncoderUsed: false,
          wasRevised: true,
          modelUsed: "gpt-4",
        },
      },
    ];

    mockFetch(() =>
      Promise.resolve({ ok: true, json: () => Promise.resolve([]) })
    );

    await renderComponent({ messages });

    expect(screen.getByText(/MEDIUM confidence/)).toBeDefined();
  });

  it("renders LOW confidence badge", async () => {
    const messages = [
      { id: 0, role: "assistant", content: "Hello!" },
      {
        id: 1,
        role: "assistant",
        content: "Analysis result",
        uncertainty: {
          level: "LOW",
          score: 0.2,
          selfConsistencyScore: null,
          verbalizedConfidence: null,
          groundingScore: null,
          crossEncoderUsed: false,
          wasRevised: false,
          modelUsed: "gpt-4",
        },
      },
    ];

    mockFetch(() =>
      Promise.resolve({ ok: true, json: () => Promise.resolve([]) })
    );

    await renderComponent({ messages });

    expect(screen.getByText(/LOW confidence/)).toBeDefined();
  });

  // ─── ConfidenceBreakdown ──────────────────────────────

  it("ConfidenceBreakdown expands and shows score bars", async () => {
    const messages = [
      { id: 0, role: "assistant", content: "Hello!" },
      {
        id: 1,
        role: "assistant",
        content: "Analysis result",
        uncertainty: {
          level: "HIGH",
          score: 0.9,
          uncertainty_score: 0.9,
          selfConsistencyScore: 0.85,
          verbalizedConfidence: 0.88,
          groundingScore: 0.92,
          crossEncoderUsed: false,
          wasRevised: false,
          modelUsed: "gpt-4",
        },
      },
    ];

    mockFetch(() =>
      Promise.resolve({ ok: true, json: () => Promise.resolve([]) })
    );

    await renderComponent({ messages });

    const breakdownBtn = screen.getByText("Confidence breakdown");
    fireEvent.click(breakdownBtn);

    await waitFor(() => {
      expect(screen.getByText("Retrieval")).toBeDefined();
      expect(screen.getByText("Consistency")).toBeDefined();
      expect(screen.getByText("Verbalized")).toBeDefined();
      expect(screen.getByText("Grounding")).toBeDefined();
    });
  });

  it("ConfidenceBreakdown collapses when clicked again", async () => {
    const messages = [
      { id: 0, role: "assistant", content: "Hello!" },
      {
        id: 1,
        role: "assistant",
        content: "Analysis result",
        uncertainty: {
          level: "HIGH",
          score: 0.9,
          uncertainty_score: 0.9,
          selfConsistencyScore: 0.85,
          verbalizedConfidence: 0.88,
          groundingScore: 0.92,
          crossEncoderUsed: false,
          wasRevised: false,
          modelUsed: "gpt-4",
        },
      },
    ];

    mockFetch(() =>
      Promise.resolve({ ok: true, json: () => Promise.resolve([]) })
    );

    await renderComponent({ messages });

    const breakdownBtn = screen.getByText("Confidence breakdown");
    fireEvent.click(breakdownBtn);
    await waitFor(() => {
      expect(screen.getByText("Retrieval")).toBeDefined();
    });

    fireEvent.click(breakdownBtn);
    await waitFor(() => {
      expect(screen.queryByText("Retrieval")).toBeNull();
    });
  });

  it("ConfidenceBreakdown filters out null scores", async () => {
    const messages = [
      { id: 0, role: "assistant", content: "Hello!" },
      {
        id: 1,
        role: "assistant",
        content: "Analysis result",
        uncertainty: {
          level: "HIGH",
          score: 0.9,
          uncertainty_score: 0.9,
          selfConsistencyScore: null,
          verbalizedConfidence: 0.88,
          groundingScore: null,
          crossEncoderUsed: false,
          wasRevised: false,
          modelUsed: "gpt-4",
        },
      },
    ];

    mockFetch(() =>
      Promise.resolve({ ok: true, json: () => Promise.resolve([]) })
    );

    await renderComponent({ messages });

    const breakdownBtn = screen.getByText("Confidence breakdown");
    fireEvent.click(breakdownBtn);

    await waitFor(() => {
      expect(screen.getByText("Retrieval")).toBeDefined();
      expect(screen.queryByText("Consistency")).toBeNull();
      expect(screen.getByText("Verbalized")).toBeDefined();
      expect(screen.queryByText("Grounding")).toBeNull();
    });
  });

  // ─── AgenticBadges ────────────────────────────────────

  it("shows Reranked badge when crossEncoderUsed is true", async () => {
    const messages = [
      { id: 0, role: "assistant", content: "Hello!" },
      {
        id: 1,
        role: "assistant",
        content: "Result",
        uncertainty: {
          level: "HIGH",
          score: 0.9,
          crossEncoderUsed: true,
          wasRevised: false,
          modelUsed: "gpt-4",
          groundingScore: 0.85,
        },
      },
    ];

    mockFetch(() =>
      Promise.resolve({ ok: true, json: () => Promise.resolve([]) })
    );

    await renderComponent({ messages });

    expect(screen.getByText("Reranked")).toBeDefined();
  });

  it("shows Revised badge when wasRevised is true", async () => {
    const messages = [
      { id: 0, role: "assistant", content: "Hello!" },
      {
        id: 1,
        role: "assistant",
        content: "Result",
        uncertainty: {
          level: "MEDIUM",
          score: 0.6,
          crossEncoderUsed: false,
          wasRevised: true,
          modelUsed: "gpt-4",
          groundingScore: 0.5,
        },
      },
    ];

    mockFetch(() =>
      Promise.resolve({ ok: true, json: () => Promise.resolve([]) })
    );

    await renderComponent({ messages });

    expect(screen.getByText("Revised after critique")).toBeDefined();
  });

  it("shows Self-reviewed badge when not revised and not cache/db_stats", async () => {
    const messages = [
      { id: 0, role: "assistant", content: "Hello!" },
      {
        id: 1,
        role: "assistant",
        content: "Result",
        uncertainty: {
          level: "HIGH",
          score: 0.9,
          crossEncoderUsed: false,
          wasRevised: false,
          modelUsed: "gpt-4",
          groundingScore: null,
        },
      },
    ];

    mockFetch(() =>
      Promise.resolve({ ok: true, json: () => Promise.resolve([]) })
    );

    await renderComponent({ messages });

    expect(screen.getByText("Self-reviewed")).toBeDefined();
  });

  it("does NOT show Self-reviewed badge when modelUsed is cache", async () => {
    const messages = [
      { id: 0, role: "assistant", content: "Hello!" },
      {
        id: 1,
        role: "assistant",
        content: "Result",
        uncertainty: {
          level: "LOW",
          score: 0.3,
          crossEncoderUsed: false,
          wasRevised: false,
          modelUsed: "cache",
          groundingScore: null,
        },
      },
    ];

    mockFetch(() =>
      Promise.resolve({ ok: true, json: () => Promise.resolve([]) })
    );

    await renderComponent({ messages });

    expect(screen.queryByText("Self-reviewed")).toBeNull();
  });

  it("does NOT show Self-reviewed badge when modelUsed is db_stats", async () => {
    const messages = [
      { id: 0, role: "assistant", content: "Hello!" },
      {
        id: 1,
        role: "assistant",
        content: "Result",
        uncertainty: {
          level: "LOW",
          score: 0.3,
          crossEncoderUsed: false,
          wasRevised: false,
          modelUsed: "db_stats",
          groundingScore: null,
        },
      },
    ];

    mockFetch(() =>
      Promise.resolve({ ok: true, json: () => Promise.resolve([]) })
    );

    await renderComponent({ messages });

    expect(screen.queryByText("Self-reviewed")).toBeNull();
  });

  it("shows Grounding badge with high score", async () => {
    const messages = [
      { id: 0, role: "assistant", content: "Hello!" },
      {
        id: 1,
        role: "assistant",
        content: "Result",
        uncertainty: {
          level: "HIGH",
          score: 0.9,
          crossEncoderUsed: false,
          wasRevised: false,
          modelUsed: "gpt-4",
          groundingScore: 0.9,
        },
      },
    ];

    mockFetch(() =>
      Promise.resolve({ ok: true, json: () => Promise.resolve([]) })
    );

    await renderComponent({ messages });

    expect(screen.getByText(/Grounding: 90%/)).toBeDefined();
  });

  it("shows Grounding badge with medium score", async () => {
    const messages = [
      { id: 0, role: "assistant", content: "Hello!" },
      {
        id: 1,
        role: "assistant",
        content: "Result",
        uncertainty: {
          level: "MEDIUM",
          score: 0.6,
          crossEncoderUsed: false,
          wasRevised: false,
          modelUsed: "gpt-4",
          groundingScore: 0.6,
        },
      },
    ];

    mockFetch(() =>
      Promise.resolve({ ok: true, json: () => Promise.resolve([]) })
    );

    await renderComponent({ messages });

    expect(screen.getByText(/Grounding: 60%/)).toBeDefined();
  });

  it("shows Grounding badge with low score", async () => {
    const messages = [
      { id: 0, role: "assistant", content: "Hello!" },
      {
        id: 1,
        role: "assistant",
        content: "Result",
        uncertainty: {
          level: "LOW",
          score: 0.3,
          crossEncoderUsed: false,
          wasRevised: false,
          modelUsed: "gpt-4",
          groundingScore: 0.3,
        },
      },
    ];

    mockFetch(() =>
      Promise.resolve({ ok: true, json: () => Promise.resolve([]) })
    );

    await renderComponent({ messages });

    expect(screen.getByText(/Grounding: 30%/)).toBeDefined();
  });

  // ─── CritiqueSection ──────────────────────────────────

  it("renders CritiqueSection when critiqueText is present", async () => {
    const messages = [
      { id: 0, role: "assistant", content: "Hello!" },
      {
        id: 1,
        role: "assistant",
        content: "Result",
        critiqueText: "The answer could be more specific about error codes.",
      },
    ];

    mockFetch(() =>
      Promise.resolve({ ok: true, json: () => Promise.resolve([]) })
    );

    await renderComponent({ messages });

    expect(screen.getByText("Show critique")).toBeDefined();
  });

  it("CritiqueSection expands to show critique text", async () => {
    const messages = [
      { id: 0, role: "assistant", content: "Hello!" },
      {
        id: 1,
        role: "assistant",
        content: "Result",
        critiqueText: "The answer could be more specific about error codes.",
      },
    ];

    mockFetch(() =>
      Promise.resolve({ ok: true, json: () => Promise.resolve([]) })
    );

    await renderComponent({ messages });

    fireEvent.click(screen.getByText("Show critique"));

    await waitFor(() => {
      expect(screen.getByText("The answer could be more specific about error codes.")).toBeDefined();
      expect(screen.getByText("Hide critique")).toBeDefined();
    });
  });

  it("CritiqueSection collapses when clicked again", async () => {
    const messages = [
      { id: 0, role: "assistant", content: "Hello!" },
      {
        id: 1,
        role: "assistant",
        content: "Result",
        critiqueText: "Needs improvement.",
      },
    ];

    mockFetch(() =>
      Promise.resolve({ ok: true, json: () => Promise.resolve([]) })
    );

    await renderComponent({ messages });

    fireEvent.click(screen.getByText("Show critique"));
    await waitFor(() => {
      expect(screen.getByText("Hide critique")).toBeDefined();
    });

    fireEvent.click(screen.getByText("Hide critique"));
    await waitFor(() => {
      expect(screen.queryByText("Needs improvement.")).toBeNull();
      expect(screen.getByText("Show critique")).toBeDefined();
    });
  });

  // ─── SourceList ────────────────────────────────────────

  it("renders SourceList when sources are present", async () => {
    const messages = [
      { id: 0, role: "assistant", content: "Hello!" },
      {
        id: 1,
        role: "assistant",
        content: "Result",
        sources: [
          { atm_id: "ATM-GB-0001", confidence_score: 0.85, timestamp: "2025-01-01T12:00:00", text: "Error log entry" },
        ],
      },
    ];

    mockFetch(() =>
      Promise.resolve({ ok: true, json: () => Promise.resolve([]) })
    );

    await renderComponent({ messages });

    expect(screen.getByText("1 source used")).toBeDefined();
  });

  it("SourceList expands to show source details", async () => {
    const messages = [
      { id: 0, role: "assistant", content: "Hello!" },
      {
        id: 1,
        role: "assistant",
        content: "Result",
        sources: [
          { atm_id: "ATM-GB-0001", confidence_score: 0.85, timestamp: "2025-01-01T12:00:00", text: "Error log entry text" },
        ],
      },
    ];

    mockFetch(() =>
      Promise.resolve({ ok: true, json: () => Promise.resolve([]) })
    );

    await renderComponent({ messages });

    fireEvent.click(screen.getByText("1 source used"));

    await waitFor(() => {
      expect(screen.getByText("ATM-GB-0001")).toBeDefined();
      expect(screen.getByText("Confidence: 85%")).toBeDefined();
      expect(screen.getByText("Error log entry text")).toBeDefined();
    });
  });

  it("SourceList collapses when clicked again", async () => {
    const messages = [
      { id: 0, role: "assistant", content: "Hello!" },
      {
        id: 1,
        role: "assistant",
        content: "Result",
        sources: [
          { atm_id: "ATM-GB-0001", confidence_score: 0.85, timestamp: "2025-01-01T12:00:00", text: "Error log entry text" },
        ],
      },
    ];

    mockFetch(() =>
      Promise.resolve({ ok: true, json: () => Promise.resolve([]) })
    );

    await renderComponent({ messages });

    const sourceBtn = screen.getByText("1 source used");
    fireEvent.click(sourceBtn);
    await waitFor(() => {
      expect(screen.getByText("ATM-GB-0001")).toBeDefined();
    });

    fireEvent.click(sourceBtn);
    await waitFor(() => {
      expect(screen.queryByText("ATM-GB-0001")).toBeNull();
    });
  });

  it("shows plural 'sources' label for multiple sources", async () => {
    const messages = [
      { id: 0, role: "assistant", content: "Hello!" },
      {
        id: 1,
        role: "assistant",
        content: "Result",
        sources: [
          { atm_id: "ATM-GB-0001", text: "Entry 1" },
          { atm_id: "ATM-GB-0002", text: "Entry 2" },
        ],
      },
    ];

    mockFetch(() =>
      Promise.resolve({ ok: true, json: () => Promise.resolve([]) })
    );

    await renderComponent({ messages });

    expect(screen.getByText("2 sources used")).toBeDefined();
  });

  it("does not render SourceList when sources is empty", async () => {
    const messages = [
      { id: 0, role: "assistant", content: "Hello!" },
      {
        id: 1,
        role: "assistant",
        content: "Result",
        sources: [],
      },
    ];

    mockFetch(() =>
      Promise.resolve({ ok: true, json: () => Promise.resolve([]) })
    );

    await renderComponent({ messages });

    expect(screen.queryByText(/source.*used/)).toBeNull();
  });

  // ─── ConfidenceBadge with score display ────────────────

  it("ConfidenceBadge shows percentage score when provided", async () => {
    const messages = [
      { id: 0, role: "assistant", content: "Hello!" },
      {
        id: 1,
        role: "assistant",
        content: "Result",
        uncertainty: {
          level: "HIGH",
          score: 0.92,
          crossEncoderUsed: false,
          wasRevised: false,
          modelUsed: "gpt-4",
          groundingScore: null,
        },
      },
    ];

    mockFetch(() =>
      Promise.resolve({ ok: true, json: () => Promise.resolve([]) })
    );

    await renderComponent({ messages });

    expect(screen.getByText(/92%/)).toBeDefined();
  });

  // ─── Loading state with no example queries ─────────────

  it("hides example queries when loading is true", async () => {
    mockFetch(() =>
      Promise.resolve({ ok: true, json: () => Promise.resolve([]) })
    );

    await renderComponent({ loading: true });

    expect(screen.queryByText("Try asking about")).toBeNull();
  });

  // ─── user message styling ─────────────────────────────

  it("renders user message with 'You' avatar", async () => {
    const messages = [
      { id: 0, role: "assistant", content: "Hello!" },
      { id: 1, role: "user", content: "What is A1?" },
    ];

    mockFetch(() =>
      Promise.resolve({ ok: true, json: () => Promise.resolve([]) })
    );

    await renderComponent({ messages });

    expect(screen.getByText("What is A1?")).toBeDefined();
    expect(screen.getByText("You")).toBeDefined();
  });

  // ─── New Chat button ──────────────────────────────────

  it("New Chat button calls handleNewChat", async () => {
    const handleNewChat = vi.fn();

    mockFetch(() =>
      Promise.resolve({ ok: true, json: () => Promise.resolve([]) })
    );

    await renderComponent({ handleNewChat });

    fireEvent.click(screen.getByText("New Chat"));

    await waitFor(() => {
      expect(handleNewChat).toHaveBeenCalled();
    });
  });

  // ─── SourceList with source without score ─────────────

  it("SourceList renders source without confidence score", async () => {
    const messages = [
      { id: 0, role: "assistant", content: "Hello!" },
      {
        id: 1,
        role: "assistant",
        content: "Result",
        sources: [
          { atm_id: "ATM-GB-0001", timestamp: "2025-01-01T12:00:00", text: "Entry" },
        ],
      },
    ];

    mockFetch(() =>
      Promise.resolve({ ok: true, json: () => Promise.resolve([]) })
    );

    await renderComponent({ messages });

    fireEvent.click(screen.getByText("1 source used"));

    await waitFor(() => {
      expect(screen.getByText("ATM-GB-0001")).toBeDefined();
      expect(screen.queryByText(/Confidence/)).toBeNull();
    });
  });

  // ─── empty history ─────────────────────────────────────

  it("shows empty history state", async () => {
    const { getRAGHistory } = await import("../api/api");
    getRAGHistory.mockResolvedValueOnce({ history: [] });

    mockFetch(() =>
      Promise.resolve({ ok: true, json: () => Promise.resolve([]) })
    );

    await renderComponent({ activeTab: "history" });

    expect(
      await screen.findByText(/No query history yet/)
    ).toBeDefined();
  });

  // ─── history with 'queries' key ────────────────────────

  it("fetchHistory handles 'queries' key from API response", async () => {
    const { getRAGHistory } = await import("../api/api");
    getRAGHistory.mockResolvedValueOnce({
      queries: [
        { id: 1, query_text: "Query via queries key", answer_text: "Answer", uncertainty_score: 0.5, created_at: "2025-01-01T12:00:00" },
      ],
    });

    mockFetch(() =>
      Promise.resolve({ ok: true, json: () => Promise.resolve([]) })
    );

    await renderComponent({ activeTab: "history" });

    expect(await screen.findByText("Query via queries key")).toBeDefined();
  });

  // ─── history with 'data' key ───────────────────────────

  it("fetchHistory handles 'data' key from API response", async () => {
    const { getRAGHistory } = await import("../api/api");
    getRAGHistory.mockResolvedValueOnce({
      data: [
        { id: 1, query_text: "Query via data key", answer_text: "Answer", uncertainty_score: 0.5, created_at: "2025-01-01T12:00:00" },
      ],
    });

    mockFetch(() =>
      Promise.resolve({ ok: true, json: () => Promise.resolve([]) })
    );

    await renderComponent({ activeTab: "history" });

    expect(await screen.findByText("Query via data key")).toBeDefined();
  });
});
