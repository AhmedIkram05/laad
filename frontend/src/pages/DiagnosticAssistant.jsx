/*
 * Diagnostic Assistant Page
 * --------------------
 * RAG-powered chat interface for ATM diagnostics with uncertainty visualization.
 * Full-page messaging layout inspired by ChatGPT/Claude.
 */

import {useState, useRef, useEffect} from "react";
import {queryRAG, submitRAGFeedback, getRAGStats, recalibrateRAG, getRAGHistory} from "../api/api";
import {useAuth} from "../auth/AuthProvider";
import UncertaintyBadge from "../components/UncertaintyBadge";
import SourceList from "../components/SourceList";
import "./DiagnosticAssistant.css";

function DiagnosticAssistant() {
    const [messages, setMessages] = useState([
        {
            id: 0,
            role: "assistant",
            content: "Hello! I'm your ATM diagnostic assistant. Ask me about any ATM issues, error messages, or anomalies. I'll analyze the log data and provide recommendations.",
            uncertainty: null,
            sources: [],
        },
    ]);
    const [input, setInput] = useState("");
    const [loading, setLoading] = useState(false);
    const [feedbackSubmitted, setFeedbackSubmitted] = useState({});
    const [stats, setStats] = useState(null);
    const [recalibrating, setRecalibrating] = useState(false);
    const [recalibrateMsg, setRecalibrateMsg] = useState("");
    const [activeTab, setActiveTab] = useState("chat");
    const [history, setHistory] = useState([]);
    const [historyLoading, setHistoryLoading] = useState(false);
    const [historyPage, setHistoryPage] = useState(0);
    const [historyTotal, setHistoryTotal] = useState(0);
    const [showSettings, setShowSettings] = useState(false);
    const messagesEndRef = useRef(null);
    const {user} = useAuth();
    const isAdmin = user && user.role === "admin";
    const HISTORY_LIMIT = 20;

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

    const handleRecalibrate = async () => {
        setRecalibrating(true);
        setRecalibrateMsg("");
        try {
            await recalibrateRAG();
            setRecalibrateMsg("Recalibration complete!");
            const data = await getRAGStats();
            setStats(data);
        } catch (err) {
            setRecalibrateMsg(`Error: ${err.message}`);
        } finally {
            setRecalibrating(false);
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
                    is_calibrated: response.is_calibrated,
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

    const handleFeedback = async (queryId, feedback) => {
        if (feedbackSubmitted[queryId]) return;
        try {
            await submitRAGFeedback(queryId, feedback);
            setFeedbackSubmitted((prev) => ({ ...prev, [queryId]: true }));
        } catch (err) {
            console.error("Failed to submit feedback:", err);
        }
    };

    const handleRetryQuery = async (queryText) => {
        setInput(queryText);
        setActiveTab("chat");
    };

    const handleNewChat = () => {
        setMessages([
            {
                id: Date.now(),
                role: "assistant",
                content: "Hello! I'm your ATM diagnostic assistant. Ask me about any ATM issues, error messages, or anomalies. I'll analyze the log data and provide recommendations.",
                uncertainty: null,
                sources: [],
            },
        ]);
        setFeedbackSubmitted({});
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
                    {isAdmin && (
                        <button className="settings-btn" onClick={() => setShowSettings(!showSettings)} title="Settings">
                            {showSettings ? "Close" : "Settings"}
                        </button>
                    )}
                </div>
            </div>

            {activeTab === "chat" && showSettings && stats && (
                <div className="settings-panel">
                    <div className="stats-row">
                        <span className="stat-label">Indexed Chunks</span>
                        <span className="stat-value">{stats.collection_chunks}</span>
                    </div>
                    <div className="stats-row">
                        <span className="stat-label">Total Queries</span>
                        <span className="stat-value">{stats.total_queries}</span>
                    </div>
                    <div className="stats-row">
                        <span className="stat-label">Feedback Samples</span>
                        <span className="stat-value">{stats.calibration_samples}</span>
                    </div>
                    <div className="stats-row">
                        <span className="stat-label">Calibrated</span>
                        <span className="stat-value">{stats.is_calibrated ? "Yes" : "No"}</span>
                    </div>
                    <button
                        className="recalibrate-btn"
                        onClick={handleRecalibrate}
                        disabled={recalibrating || stats.calibration_samples < 20}
                    >
                        {recalibrating ? "Recalibrating..." : "Recalibrate"}
                    </button>
                    {recalibrateMsg && <span className="recalibrate-msg">{recalibrateMsg}</span>}
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
                                    <div className="message-content">{msg.content}</div>

                                    {msg.role === "assistant" && msg.uncertainty && (
                                        <div className="message-meta">
                                            <UncertaintyBadge
                                                level={msg.uncertainty.level}
                                                score={msg.uncertainty.score}
                                                isCalibrated={msg.uncertainty.is_calibrated}
                                            />
                                            <span className="recommendation">
                                                {msg.uncertainty.recommendation}
                                            </span>
                                        </div>
                                    )}

                                    {msg.role === "assistant" && msg.sources?.length > 0 && (
                                        <SourceList sources={msg.sources} />
                                    )}

                                    {msg.role === "assistant" && msg.query_id && (
                                        <div className="feedback-buttons">
                                            <button
                                                onClick={() => handleFeedback(msg.query_id, "helpful")}
                                                title="This was helpful"
                                                disabled={feedbackSubmitted[msg.query_id]}
                                            >
                                                Helpful
                                            </button>
                                            <button
                                                onClick={() => handleFeedback(msg.query_id, "not_helpful")}
                                                title="This wasn't helpful"
                                                disabled={feedbackSubmitted[msg.query_id]}
                                            >
                                                Not helpful
                                            </button>
                                        </div>
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
