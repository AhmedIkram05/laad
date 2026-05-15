/*
 * RAG History Page
 * --------------------
 * Displays past RAG queries with answers and uncertainty scores.
 */

import {useState, useEffect} from "react";
import {getRAGHistory} from "../api/api";
import "./RAGHistory.css";

function RAGHistory() {
    const [history, setHistory] = useState([]);
    const [loading, setLoading] = useState(true);
    const [total, setTotal] = useState(0);
    const [offset, setOffset] = useState(0);
    const limit = 20;

    const fetchHistory = async () => {
        setLoading(true);
        try {
            const data = await getRAGHistory(limit, offset);
            setHistory(data.history || []);
            setTotal(data.total || 0);
        } catch (err) {
            console.error("Failed to fetch history:", err);
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        fetchHistory();
    }, [offset]);

    const formatDate = (iso) => {
        if (!iso) return "Unknown";
        return new Date(iso).toLocaleString();
    };

    return (
        <div className="rag-history">
            <div className="history-header">
                <h1>Query History</h1>
                <p>{total} total queries</p>
            </div>

            {loading ? (
                <div className="loading">Loading history...</div>
            ) : history.length === 0 ? (
                <div className="empty">No queries yet. Ask something in the Diagnostic Assistant.</div>
            ) : (
                <div className="history-list">
                    {history.map((item) => (
                        <div key={item.id} className="history-card">
                            <div className="history-meta">
                                <span className="history-date">{formatDate(item.created_at)}</span>
                                <span className="history-score">
                                    Confidence: {(item.uncertainty_score * 100).toFixed(0)}%
                                </span>
                            </div>
                            <div className="history-query">
                                <strong>Q:</strong> {item.query_text}
                            </div>
                            <div className="history-answer">
                                <strong>A:</strong> {item.answer_text}
                            </div>
                        </div>
                    ))}
                </div>
            )}

            <div className="pagination">
                <button
                    disabled={offset === 0}
                    onClick={() => setOffset((o) => Math.max(0, o - limit))}
                >
                    Previous
                </button>
                <span>{offset + 1}–{Math.min(offset + limit, total)} of {total}</span>
                <button
                    disabled={offset + limit >= total}
                    onClick={() => setOffset((o) => o + limit)}
                >
                    Next
                </button>
            </div>
        </div>
    );
}

export default RAGHistory;
