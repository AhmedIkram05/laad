/*
 * Diagnostic Assistant Page
 * --------------------
 * RAG-powered chat interface for ATM diagnostics with uncertainty visualization.
 * Full-page messaging layout inspired by ChatGPT/Claude.
 */

import {useState, useRef, useEffect} from "react";
import {queryRAG, getRAGStats, getRAGHistory} from "../api/api";
import UncertaintyBadge from "../components/UncertaintyBadge";
import SourceList from "../components/SourceList";
import MarkdownRenderer from "../components/MarkdownRenderer";
import "./DiagnosticAssistant.css";

function DiagnosticAssistant() {
    const [messages, setMessages] = useState(() => {
        try {
            const saved = localStorage.getItem("rag_chat_messages");
            if (saved) {
                const parsed = JSON.parse(saved);
                if (Array.isArray(parsed) && parsed.length > 0) {
                    return parsed;
                }
            }
        } catch {
            // ignore
        }
        return [{
            id: 0,
            role: "assistant",
            content: "Hello! I'm your ATM diagnostic assistant. Ask me about any ATM issues, error messages, or anomalies. I'll analyze the log data and provide recommendations.",
            uncertainty: null,
            sources: [],
        }];
    });
    const [input, setInput] = useState(() => {
        try {
            return localStorage.getItem("rag_chat_input") || "";
        } catch {
            return "";
        }
    });
    const [loading, setLoading] = useState(false);
    const [stats, setStats] = useState(null);
    const [activeTab, setActiveTab] = useState("chat");
    const [history, setHistory] = useState([]);
    const [historyLoading, setHistoryLoading] = useState(false);
    const [historyPage, setHistoryPage] = useState(0);
    const [historyTotal, setHistoryTotal] = useState(0);
    const messagesEndRef = useRef(null);
    const HISTORY_LIMIT = 20;

    const STORAGE_KEY_MESSAGES = "rag_chat_messages";
    const STORAGE_KEY_INPUT = "rag_chat_input";
    const MAX_STORAGE_SIZE = 4 * 1024 * 1024;

    useEffect(() => {
        if (messages.length > 0) {
            try {
                const jsonStr = JSON.stringify(messages);
                if (jsonStr.length > MAX_STORAGE_SIZE) {
                    const trimmed = messages.slice(-50);
                    const trimmedJson = JSON.stringify(trimmed);
                    localStorage.setItem(STORAGE_KEY_MESSAGES, trimmedJson);
                } else {
                    localStorage.setItem(STORAGE_KEY_MESSAGES, jsonStr);
                }
            } catch (e) {
                if (e.name === "QuotaExceededError") {
                    const trimmed = messages.slice(-20);
                    localStorage.setItem(STORAGE_KEY_MESSAGES, JSON.stringify(trimmed));
                }
            }
        }
    }, [messages, MAX_STORAGE_SIZE]);

    useEffect(() => {
        try {
            localStorage.setItem(STORAGE_KEY_INPUT, input);
        } catch {
            // Ignore storage errors
        }
    }, [input]);

    useEffect(() => {
        messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
    }, [messages]);

    useEffect(() => {
        const fetchStats = async () => {
            try {
                const data = await getRAGStats();
                setStats(data);
            } catch (err) {
                console.error("Failed to fetch stats:", err);
            }
        };
        fetchStats();
    }, []);

    useEffect(() => {
        if (activeTab === "history") {
            fetchHistory(0);
        }
    }, [activeTab]);

    const fetchHistory = async (page) => {
        setHistoryLoading(true);
        try {
            const data = await getRAGHistory(HISTORY_LIMIT, page * HISTORY_LIMIT);
            setHistory(data.history || []);
            setHistoryTotal(data.total || 0);
            setHistoryPage(page);
        } catch (err) {
            console.error("Failed to fetch history:", err);
            setHistory([]);
        } finally {
            setHistoryLoading(false);
        }
    };

    const handleSubmit = async (e) => {
        e.preventDefault();
        if (!input.trim() || loading) return;

        const userMessage = {
            id: Date.now(),
            role: "user",
            content: input,
        };
        setMessages((prev) => [...prev, userMessage]);
        setInput("");
        setLoading(true);

        try {
            const response = await queryRAG(input, null, 5, true);

            const assistantMessage = {
                id: Date.now() + 1,
                role: "assistant",
                content: response.answer,
                uncertainty: {
                    score: response.uncertainty_score,
                    level: response.confidence_level,
                    is_uncertain: response.is_uncertain,
                    recommendation: response.recommendation,
                },
                sources: response.sources || [],
                query_id: response.query_id,
            };

            setMessages((prev) => [...prev, assistantMessage]);
        } catch (err) {
            setMessages((prev) => [
                ...prev,
                {
                    id: Date.now() + 1,
                    role: "assistant",
                    content: `Error: ${err.message}`,
                    uncertainty: null,
                    sources: [],
                },
            ]);
        } finally {
            setLoading(false);
        }
    };

    const handleRetryQuery = async (queryText) => {
        setInput(queryText);
        setActiveTab("chat");
    };

    const handleNewChat = () => {
        localStorage.removeItem(STORAGE_KEY_MESSAGES);
        localStorage.removeItem(STORAGE_KEY_INPUT);
        setMessages([{
            id: 0,
            role: "assistant",
            content: "Hello! I'm your ATM diagnostic assistant. Ask me about any ATM issues, error messages, or anomalies. I'll analyze the log data and provide recommendations.",
            uncertainty: null,
            sources: [],
        }]);
        setInput("");
    };

    const isWelcomeScreen = messages.length <= 1;

    return (
        <div className="diagnostic-assistant">
            <div className="chat-header">
                <div className="header-left">
                    <div className="tab-switcher">
                        <button
                            className={`tab-btn ${activeTab === "chat" ? "active" : ""}`}
                            onClick={() => setActiveTab("chat")}
                        >
                            Chat
                        </button>
                        <button
                            className={`tab-btn ${activeTab === "history" ? "active" : ""}`}
                            onClick={() => setActiveTab("history")}
                        >
                            History
                        </button>
                    </div>
                </div>
                <div className="header-right">
                    {activeTab === "chat" && (
                        <button className="new-chat-btn" onClick={handleNewChat} title="New chat">
                            + New
                        </button>
                    )}
                </div>
            </div>

            {stats && (
                <div className="settings-panel">
                    <div className="stats-row">
                        <span className="stat-label">Indexed Chunks</span>
                        <span className="stat-value">{stats.collection_chunks}</span>
                    </div>
                    <div className="stats-row">
                        <span className="stat-label">Total Queries</span>
                        <span className="stat-value">{stats.total_queries}</span>
                    </div>
                </div>
            )}

            {activeTab === "chat" && (
                <div className="chat-body">
                    <div className="messages">
                        {messages.map((msg) => (
                            <div key={msg.id} className={`message-row ${msg.role}`}>
                                <div className="message-avatar">
                                    {msg.role === "user" ? "You" : "AI"}
                                </div>
                                <div className="message-bubble">
                                    <div className="message-content">
                                    <MarkdownRenderer content={msg.content} />
                                </div>

                                    {msg.role === "assistant" && msg.uncertainty && (
                                        <div className="message-meta">
                                            <UncertaintyBadge
                                                level={msg.uncertainty.level}
                                                score={msg.uncertainty.score}
                                            />
                                            <span className="recommendation">
                                                {msg.uncertainty.recommendation}
                                            </span>
                                        </div>
                                    )}

                                    {msg.role === "assistant" && msg.sources?.length > 0 && (
                                        <SourceList sources={msg.sources} />
                                    )}
                                </div>
                            </div>
                        ))}

                        {loading && (
                            <div className="message-row assistant">
                                <div className="message-avatar">AI</div>
                                <div className="message-bubble">
                                    <div className="message-content">
                                        <span className="typing-indicator">Analyzing logs and generating response...</span>
                                    </div>
                                </div>
                            </div>
                        )}
                        <div ref={messagesEndRef} />
                    </div>

                    {isWelcomeScreen && !loading && (
                        <div className="welcome-section">
                            <h2>ATM Diagnostic Assistant</h2>
                            <p>Ask questions about ATM issues, anomalies, and troubleshooting</p>
                            <div className="example-queries">
                                <button onClick={() => setInput("What does anomaly type A1 mean?")}>
                                    What does anomaly type A1 mean?
                                </button>
                                <button onClick={() => setInput("How do I fix a cash cassette empty error?")}>
                                    How do I fix a cash cassette empty error?
                                </button>
                                <button onClick={() => setInput("Show me recent network timeout issues")}>
                                    Show me recent network timeout issues
                                </button>
                                <button onClick={() => setInput("What's causing high response times on ATM-GB-0001?")}>
                                    What's causing high response times on ATM-GB-0001?
                                </button>
                            </div>
                        </div>
                    )}

                    <div className="input-area">
                        <form className="input-form" onSubmit={handleSubmit}>
                            <input
                                type="text"
                                value={input}
                                onChange={(e) => setInput(e.target.value)}
                                placeholder="Ask about ATM errors, anomalies, or troubleshooting..."
                                disabled={loading}
                            />
                            <button type="submit" disabled={loading || !input.trim()}>
                                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                                    <line x1="22" y1="2" x2="11" y2="13"></line>
                                    <polygon points="22 2 15 22 11 13 2 9 22 2"></polygon>
                                </svg>
                            </button>
                        </form>
                    </div>
                </div>
            )}

            {activeTab === "history" && (
                <div className="history-body">
                    {historyLoading ? (
                        <div className="history-loading">Loading history...</div>
                    ) : history.length === 0 ? (
                        <div className="history-empty">
                            <div className="empty-icon">
                                <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                                    <circle cx="12" cy="12" r="10"></circle>
                                    <polyline points="12 6 12 12 16 14"></polyline>
                                </svg>
                            </div>
                            <p>No query history found.</p>
                            <span>Start a conversation in the Chat tab to see history here.</span>
                        </div>
                    ) : (
                        <>
                            <div className="history-list">
                                {history.map((item) => (
                                    <div key={item.id} className="history-item">
                                        <div className="history-item-header">
                                            <span className="history-time">
                                                {new Date(item.created_at).toLocaleString()}
                                            </span>
                                            <span className="history-score">
                                                {(item.uncertainty_score * 100).toFixed(0)}% confidence
                                            </span>
                                        </div>
                                        <div className="history-query">{item.query_text}</div>
                                        <div className="history-answer">{item.answer_text}</div>
                                        <div className="history-item-footer">
                                            <button
                                                className="history-retry-btn"
                                                onClick={() => handleRetryQuery(item.query_text)}
                                            >
                                                Retry query
                                            </button>
                                        </div>
                                    </div>
                                ))}
                            </div>
                            <div className="history-pagination">
                                <button
                                    disabled={historyPage === 0}
                                    onClick={() => fetchHistory(historyPage - 1)}
                                >
                                    Previous
                                </button>
                                <span>
                                    Page {historyPage + 1} of {Math.ceil(historyTotal / HISTORY_LIMIT)}
                                </span>
                                <button
                                    disabled={(historyPage + 1) * HISTORY_LIMIT >= historyTotal}
                                    onClick={() => fetchHistory(historyPage + 1)}
                                >
                                    Next
                                </button>
                            </div>
                        </>
                    )}
                </div>
            )}
        </div>
    );
}

export default DiagnosticAssistant;
