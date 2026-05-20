/*
 * SourceList Component
 * --------------------
 * Displays retrieved log sources with per-item expand/collapse and expand-all control.
 */

import {useState} from "react";
import "./SourceList.css";

function SourceList({sources}) {
    const [expanded, setExpanded] = useState({});
    const [allExpanded, setAllExpanded] = useState(false);

    const toggleExpand = (index) => {
        setExpanded((prev) => ({...prev, [index]: !prev[index]}));
    };

    const toggleAll = () => {
        const next = !allExpanded;
        setAllExpanded(next);
        const allStates = {};
        sources.forEach((_, i) => {
            allStates[i] = next;
        });
        setExpanded(allStates);
    };

    if (!sources || sources.length === 0) return null;

    const allAreExpanded = sources.length > 0 && sources.every((_, i) => expanded[i]);

    return (
        <div className="source-list">
            <div className="source-header">
                <span className="source-title">Retrieved Context</span>
                <div className="source-header-right">
                    <span className="source-count">{sources.length} sources</span>
                    {sources.length > 1 && (
                        <button className="expand-all-btn" onClick={toggleAll}>
                            {allAreExpanded ? "Collapse All" : "Expand All"}
                        </button>
                    )}
                </div>
            </div>
            <div className="sources">
                {sources.map((source, index) => (
                    <div
                        key={source.chunk_id || index}
                        className={`source-item ${expanded[index] ? "expanded" : ""}`}
                    >
                        <button
                            className="source-summary"
                            onClick={() => toggleExpand(index)}
                            aria-expanded={!!expanded[index]}
                        >
                            <span className="source-atm">
                                {source.atm_id || "Unknown ATM"}
                            </span>
                            {source.timestamp && (
                                <span className="source-time">
                                    {new Date(source.timestamp).toLocaleString()}
                                </span>
                            )}
                            <span
                                className="source-confidence"
                                style={{
                                    color:
                                        source.confidence_score >= 0.8
                                            ? "#10b981"
                                            : source.confidence_score >= 0.5
                                            ? "#f59e0b"
                                            : "#ef4444",
                                }}
                            >
                                {(source.confidence_score * 100).toFixed(0)}% match
                            </span>
                            <span className="expand-hint">
                                {expanded[index] ? "▲" : "▼"}
                            </span>
                        </button>
                        <div className={`source-text ${expanded[index] ? "expanded" : ""}`}>
                            {source.text}
                        </div>
                    </div>
                ))}
            </div>
        </div>
    );
}

export default SourceList;