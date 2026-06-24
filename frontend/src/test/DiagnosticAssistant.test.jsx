import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

describe("DiagnosticAssistant", () => {
  beforeEach(() => {
    vi.resetModules();
    vi.restoreAllMocks();
  });

  const mockMessages = [
    { id: 0, role: "assistant", content: "Hello! I'm your ATM diagnostic assistant." },
  ];

  async function renderDiagnostic(contextValue) {
    const { RAGContext } = await import("../providers/RAGProvider");
    const { default: DiagnosticAssistant } = await import("../pages/DiagnosticAssistant");
    return render(
      <RAGContext.Provider value={contextValue}>
        <MemoryRouter>
          <DiagnosticAssistant />
        </MemoryRouter>
      </RAGContext.Provider>
    );
  }

  it("renders chat interface", async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve([]),
    });

    await renderDiagnostic({
      messages: mockMessages,
      input: "",
      setInput: vi.fn(),
      loading: false,
      activeTab: "chat",
      setActiveTab: vi.fn(),
      submitQuery: vi.fn(),
      handleNewChat: vi.fn(),
      setMessages: vi.fn(),
    });
    expect(screen.getByText("Chat")).toBeDefined();
  });

  it("shows chat and history tabs", async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve([]),
    });

    await renderDiagnostic({
      messages: mockMessages,
      input: "",
      setInput: vi.fn(),
      loading: false,
      activeTab: "chat",
      setActiveTab: vi.fn(),
      submitQuery: vi.fn(),
      handleNewChat: vi.fn(),
      setMessages: vi.fn(),
    });
    expect(screen.getByText("Chat")).toBeDefined();
    expect(screen.getByText("History")).toBeDefined();
  });

  it("shows initial assistant message", async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve([]),
    });

    await renderDiagnostic({
      messages: mockMessages,
      input: "",
      setInput: vi.fn(),
      loading: false,
      activeTab: "chat",
      setActiveTab: vi.fn(),
      submitQuery: vi.fn(),
      handleNewChat: vi.fn(),
      setMessages: vi.fn(),
    });
    expect(screen.getByText(/ATM diagnostic assistant/i)).toBeDefined();
  });

  it("has new chat button", async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve([]),
    });

    const handleNewChat = vi.fn();
    await renderDiagnostic({
      messages: mockMessages,
      input: "",
      setInput: vi.fn(),
      loading: false,
      activeTab: "chat",
      setActiveTab: vi.fn(),
      submitQuery: vi.fn(),
      handleNewChat,
      setMessages: vi.fn(),
    });

    const newChatBtn = screen.getByText("New Chat");
    expect(newChatBtn).toBeDefined();
    fireEvent.click(newChatBtn);
    expect(handleNewChat).toHaveBeenCalled();
  });

  it("shows example queries when no messages yet", async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve([]),
    });

    await renderDiagnostic({
      messages: mockMessages,
      input: "",
      setInput: vi.fn(),
      loading: false,
      activeTab: "chat",
      setActiveTab: vi.fn(),
      submitQuery: vi.fn(),
      handleNewChat: vi.fn(),
      setMessages: vi.fn(),
    });

    expect(screen.getByText("Try asking about")).toBeDefined();
    expect(screen.getByText("What does anomaly type A1 mean?")).toBeDefined();
  });

  it("has submit button and input field", async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve([]),
    });

    await renderDiagnostic({
      messages: mockMessages,
      input: "",
      setInput: vi.fn(),
      loading: false,
      activeTab: "chat",
      setActiveTab: vi.fn(),
      submitQuery: vi.fn(),
      handleNewChat: vi.fn(),
      setMessages: vi.fn(),
    });

    expect(screen.getByPlaceholderText(/Ask about ATM errors/i)).toBeDefined();
    expect(screen.getByText("Send")).toBeDefined();
  });

  it("shows typing indicator when loading", async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve([]),
    });

    await renderDiagnostic({
      messages: mockMessages,
      input: "",
      setInput: vi.fn(),
      loading: true,
      activeTab: "chat",
      setActiveTab: vi.fn(),
      submitQuery: vi.fn(),
      handleNewChat: vi.fn(),
      setMessages: vi.fn(),
    });

    // Typing indicator dots should be present when loading
    const dots = document.querySelectorAll(".animate-bounce");
    expect(dots.length).toBeGreaterThanOrEqual(2);
  });

  it("shows empty history state in history tab", async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ data: [], total: 0 }),
    });

    await renderDiagnostic({
      messages: mockMessages,
      input: "",
      setInput: vi.fn(),
      loading: false,
      activeTab: "history",
      setActiveTab: vi.fn(),
      submitQuery: vi.fn(),
      handleNewChat: vi.fn(),
      setMessages: vi.fn(),
    });

    const emptyMsg = await screen.findByText(/No query history yet/i, {}, { timeout: 3000 });
    expect(emptyMsg).toBeDefined();
  });
});
