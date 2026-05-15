/*
 * SourceList Component
 * --------------------
 * Displays retrieved log sources with confidence scores.
 */

import {useState} from "react";
import "./SourceList.css";

function SourceList({sources}) {
    const [expanded, setExpanded] = useState({});

    const toggleExpand = (index) => {
        setExpanded((prev) => ({...prev, [index]: !prev[index]}));
    };

    if (!sources || sources.length === 0) return null;

    return (
        <div className="source-list">
            <div className="source-header">
                <span className="source-title">Retrieved Context</span>
                <span className="source-count">{sources.length} sources</span>
            </div>
            <div className="sources">
                {sources.map((source, index) => (
                    <div
                        key={source.chunk_id || index}
                        className="source-item"
                        onClick={() => toggleExpand(index)}
                    >
                        <div className="source-summary">
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
                        </div>
                        <div
                            className={`source-text ${expanded[index] ? "expanded" : ""}`}
                        >
                            {source.text.length > 200 && !expanded[index]
                                ? source.text.substring(0, 200) + "..."
                                : source.text}
                        </div>
                        {source.text.length > 200 && (
                            <span className="expand-hint">
                                {expanded[index] ? "Show less" : "Show more"}
                            </span>
                        )}
                    </div>
                ))}
            </div>
        </div>
    );
}

export default SourceList;