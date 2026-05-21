import { createContext, useState, useRef, useEffect, useCallback } from "react";
import { queryRAG } from "../api/api";
import { toast } from "sonner";

const RAGContext = createContext(null);

const INITIAL_MESSAGE = {
  id: 0,
  role: "assistant",
  content: "Hello! I'm your ATM diagnostic assistant. Ask me about any ATM issues, error messages, or anomalies. I'll analyse the log data and provide recommendations.",
};

const MAX_STORED_MESSAGES = 50;
const STORAGE_KEYS = {
  messages: "rag_messages",
  input: "rag_input",
  activeTab: "rag_active_tab",
};

function loadFromStorage(key, fallback) {
  try {
    const raw = window.localStorage.getItem(key);
    return raw ? JSON.parse(raw) : fallback;
  } catch {
    return fallback;
  }
}

function saveToStorage(key, value) {
  try {
    window.localStorage.setItem(key, JSON.stringify(value));
  } catch (err) {
    console.warn("localStorage write failed:", err);
  }
}

export function RAGProvider({ children }) {
  const [messages, setMessagesState] = useState(() =>
    loadFromStorage(STORAGE_KEYS.messages, [INITIAL_MESSAGE])
  );
  const [input, setInputState] = useState(() =>
    loadFromStorage(STORAGE_KEYS.input, "")
  );
  const [activeTab, setActiveTabState] = useState(() =>
    loadFromStorage(STORAGE_KEYS.activeTab, "chat")
  );
  const [loading, setLoading] = useState(false);
  const loadingRef = useRef(false);

  const persistMessages = useCallback((updater) => {
    setMessagesState((prev) => {
      const next = updater instanceof Function ? updater(prev) : updater;
      const trimmed = next.slice(-MAX_STORED_MESSAGES);
      saveToStorage(STORAGE_KEYS.messages, trimmed);
      return trimmed;
    });
  }, []);

  const setInput = useCallback((value) => {
    setInputState((prev) => {
      const resolved = value instanceof Function ? value(prev) : value;
      saveToStorage(STORAGE_KEYS.input, resolved);
      return resolved;
    });
  }, []);

  const setActiveTab = useCallback((value) => {
    setActiveTabState((prev) => {
      const resolved = value instanceof Function ? value(prev) : value;
      saveToStorage(STORAGE_KEYS.activeTab, resolved);
      return resolved;
    });
  }, []);

  const submitQuery = useCallback(async (queryText) => {
    if (!queryText?.trim() || loadingRef.current) return;

    const userMsg = { id: Date.now(), role: "user", content: queryText };

    persistMessages((prev) => [...prev, userMsg]);
    setInput("");
    loadingRef.current = true;
    setLoading(true);

    try {
      const response = await queryRAG(queryText, null, 10, true);
      const assistantMsg = {
        id: Date.now() + 1,
        role: "assistant",
        content: response.answer,
        uncertainty: {
          level: response.confidence_level,
          score: response.uncertainty_score,
          selfConsistencyScore: response.self_consistency_score,
          verbalizedConfidence: response.verbalized_confidence,
          groundingScore: response.grounding_score,
          crossEncoderUsed: response.cross_encoder_used,
          wasRevised: response.was_revised,
          modelUsed: response.model_used,
        },
        sources: response.sources || [],
        critiqueText: response.critique_text,
      };
      persistMessages((prev) => [...prev, assistantMsg]);
    } catch (err) {
      persistMessages((prev) => [
        ...prev,
        { id: Date.now() + 1, role: "assistant", content: `Error: ${err.message}` },
      ]);
      toast.error("Failed to get response");
    } finally {
      loadingRef.current = false;
      setLoading(false);
    }
  }, [persistMessages, setInput]);

  const handleNewChat = useCallback(() => {
    persistMessages([INITIAL_MESSAGE]);
    setInput("");
    setActiveTab("chat");
  }, [persistMessages, setInput, setActiveTab]);

  useEffect(() => {
    return () => {
      loadingRef.current = false;
    };
  }, []);

  return (
    <RAGContext.Provider
      value={{
        messages,
        setMessages: persistMessages,
        input,
        setInput,
        loading,
        setLoading,
        activeTab,
        setActiveTab,
        submitQuery,
        handleNewChat,
      }}
    >
      {children}
    </RAGContext.Provider>
  );
}

export { RAGContext };
