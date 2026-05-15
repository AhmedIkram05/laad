/*
 * Diagnostic Assistant Page
 * --------------------
 * RAG-powered chat interface for ATM diagnostics with uncertainty visualization.
 */

import {useState, useRef, useEffect} from "react";
import {queryRAG, submitRAGFeedback, getRAGStats, recalibrateRAG} from "../api/api";
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
    const messagesEndRef = useRef(null);
    const {user} = useAuth();
    const isAdmin = user && user.role === "admin";

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

    return (
        <div className="diagnostic-assistant">
            <div className="assistant-header">
                <h1>Diagnostic Assistant</h1>
                <p>Ask questions about ATM issues and get AI-powered analysis with confidence scores</p>
            </div>

            {stats && (
                <div className="stats-bar">
                    <div className="stat-item">
                        <span className="stat-value">{stats.total_chunks}</span>
                        <span className="stat-label">Indexed Chunks</span>
                    </div>
                    <div className="stat-item">
                        <span className="stat-value">{stats.total_queries}</span>
                        <span className="stat-label">Total Queries</span>
                    </div>
                    <div className="stat-item">
                        <span className="stat-value">{stats.calibration_samples}</span>
                        <span className="stat-label">Feedback Samples</span>
                    </div>
                    <div className="stat-item">
                        <span className="stat-value">{stats.is_calibrated ? "Yes" : "No"}</span>
                        <span className="stat-label">Calibrated</span>
                    </div>
                    {isAdmin && (
                        <div className="stat-item stat-action">
                            <button
                                onClick={handleRecalibrate}
                                disabled={recalibrating || stats.calibration_samples < 20}
                                title={stats.calibration_samples < 20 ? "Need at least 20 feedback samples" : "Recalibrate confidence calibration"}
                            >
                                {recalibrating ? "Recalibrating..." : "Recalibrate"}
                            </button>
                            {recalibrateMsg && <span className="recalibrate-msg">{recalibrateMsg}</span>}
                        </div>
                    )}
                </div>
            )}

            <div className="chat-container">
                <div className="messages">
                    {messages.map((msg) => (
                        <div key={msg.id} className={`message ${msg.role}`}>
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
                                        👍 Helpful
                                    </button>
                                    <button
                                        onClick={() => handleFeedback(msg.query_id, "not_helpful")}
                                        title="This wasn't helpful"
                                        disabled={feedbackSubmitted[msg.query_id]}
                                    >
                                        👎 Not helpful
                                    </button>
                                </div>
                            )}
                        </div>
                    ))}

                    {loading && (
                        <div className="message assistant loading">
                            <div className="message-content">
                                <span className="typing-indicator">Analyzing logs and generating response...</span>
                            </div>
                        </div>
                    )}
                    <div ref={messagesEndRef} />
                </div>

                <form className="input-form" onSubmit={handleSubmit}>
                    <input
                        type="text"
                        value={input}
                        onChange={(e) => setInput(e.target.value)}
                        placeholder="Ask about ATM errors, anomalies, or troubleshooting..."
                        disabled={loading}
                    />
                    <button type="submit" disabled={loading || !input.trim()}>
                        {loading ? "..." : "Send"}
                    </button>
                </form>
            </div>

            <div className="example-queries">
                <h3>Example Questions</h3>
                <div className="examples">
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
        </div>
    );
}

export default DiagnosticAssistant;
