/*
 * AnomalyData Page
 * --------------------
 * Displays detailed analysis for a single anomaly, including detection
 * source, confidence score, sources involved, and recommended action.
 */

/* External Libraries */
import { useParams } from "react-router-dom";
import { useEffect, useState } from "react";
import { GoStar, GoCheckCircle } from "react-icons/go";

/* Internal Imports */
import { fetchAnomalies, fetchDetailedAnalysis, toggleComplete, toggleStar } from "../api/api";
import BackButton from "../components/BackButton";
import "./AnomalyData.css";

const SOURCE_LABELS = {
    HEURISTIC: { label: "Heuristic", color: "#2563eb" },
    RULES:     { label: "Rule-Based", color: "#7c3aed" },
    ML:        { label: "ML Detected", color: "#059669" },
};

function SectionBox({ title, children, rightSlot }) {
    return (
        <section className="anomaly-section-box">
            <div className="anomaly-section-box__header">
                <h2 className="anomaly-section-box__title">{title}</h2>
                {rightSlot ? <div>{rightSlot}</div> : null}
            </div>
            <div className="anomaly-section-box__body">{children}</div>
        </section>
    );
}

function ActionButton({ label, primary = false, completed = false, icon, onClick }) {
    return (
        <button
            onClick={onClick}
            className={`anomaly-action-button
                ${primary ? "anomaly-action-button--primary" : "anomaly-action-button--secondary"}
                ${completed ? "anomaly-action-button--completed" : ""}`}
        >
            {icon && <span className="buttonIcon">{icon}</span>}
            <span>{label}</span>
        </button>
    );
}

function DetectionSourceBadge({ source }) {
    const info = SOURCE_LABELS[source] || { label: source || "Unknown", color: "#6b7280" };
    return (
        <span
            className="detection-source-badge"
            style={{ backgroundColor: info.color + "22", color: info.color, borderColor: info.color }}
        >
            {info.label}
        </span>
    );
}

function ConfidenceBar({ score }) {
    if (score === null || score === undefined) return null;
    const pct = Math.round((score || 0) * 100);
    const color = pct >= 80 ? "#059669" : pct >= 60 ? "#d97706" : "#dc2626";
    return (
        <div className="confidence-bar-container">
            <div className="confidence-bar-labels">
                <span className="confidence-label">Confidence</span>
                <span className="confidence-pct">{pct}%</span>
            </div>
            <div className="confidence-bar-track">
                <div
                    className="confidence-bar-fill"
                    style={{ width: `${pct}%`, backgroundColor: color }}
                />
            </div>
        </div>
    );
}

function SourcesChips({ sources }) {
    if (!sources || (Array.isArray(sources) && sources.length === 0)) return null;
    const list = Array.isArray(sources) ? sources : [];
    return (
        <div className="sources-chips">
            <span className="sources-label">Sources:</span>
            {list.map((s) => (
                <span key={s} className="source-chip">{s}</span>
            ))}
        </div>
    );
}

function formatEventTime(range) {
    if (!range) return "Unknown";
    const [startStr] = range.split(" - ");
    const start = new Date(startStr);
    const dateOptions = { day: "numeric", month: "short", year: "numeric" };
    const timeOptions = { hour: "2-digit", minute: "2-digit", hour12: false };
    const date = start.toLocaleDateString("en-GB", dateOptions);
    const time = start.toLocaleTimeString("en-GB", timeOptions);
    return `${date}, ${time}`;
}

function AnomalyData() {
    const { anomaly_type } = useParams();
    const [data, setData] = useState(null);
    const [isCompleted, setIsCompleted] = useState(true);
    const [isStarred, setIsStarred] = useState(false);
    const [dbAnomaly, setDbAnomaly] = useState(null);

    const handleComplete = async () => {
        if (!dbAnomaly) return;
        try {
            await toggleComplete(dbAnomaly.id);
            setIsCompleted(prev => !prev);
        } catch (err) {
            console.error("Failed to resolve anomaly", err);
        }
    };

    const handleStar = async () => {
        if (!dbAnomaly) return;
        try {
            await toggleStar(dbAnomaly.id);
            setIsStarred(prev => !prev);
        } catch (err) {
            console.error("Failed to toggle star", err);
        }
    };

    useEffect(() => {
        const load = async () => {
            try {
                const [analysisRes, anomaliesRes] = await Promise.all([
                    fetchDetailedAnalysis(anomaly_type),
                    fetchAnomalies(),
                ]);

                const analysis = analysisRes.data.find(
                    (item) => item.Anomaly === anomaly_type
                ) || analysisRes.data[0];

                const matchedAnomaly = anomaliesRes.data.find(
                    (a) => a.anomaly_type === anomaly_type
                );

                if (analysis) {
                    setData(analysis);
                }

                if (matchedAnomaly) {
                    setIsStarred(matchedAnomaly.is_starred === 1);
                    setIsCompleted(matchedAnomaly.is_active === 0);
                    setDbAnomaly(matchedAnomaly);
                }
            } catch (err) {
                console.error("Failed to fetch data", err);
            }
        };

        load();
    }, [anomaly_type]);

    if (!data) return <p>Loading...</p>;

    const confidence = data.model_confidence_score ?? dbAnomaly?.model_confidence_score ?? null;
    const detectionSource = data.detection_source ?? dbAnomaly?.explanation ?
        (() => {
            try {
                const exp = typeof dbAnomaly.explanation === "string" ?
                    JSON.parse(dbAnomaly.explanation) : dbAnomaly.explanation;
                return exp?.source || null;
            } catch { return null; }
        })() : null;
    const sources = data.sources_involved ?? dbAnomaly?.sources_involved ?? [];
    const recommendedAction = data.recommended_action || data.Recommended_Action;

    return (
        <div className="anomaly-page">
            <div className="anomaly-page__inner">

                <div className="anomaly-page__header">
                    <div className="back-button-container"><BackButton/></div>

                    <div className="anomaly-page__text">
                        <div className="anomaly-page__title-row">
                            <h1 className="anomaly-page__title">{data.Title || "Title Unknown"}</h1>
                            <DetectionSourceBadge source={detectionSource} />
                        </div>
                        <p className="anomaly-page__subtitle">
                            Review analysis, understand the ATM issue, and follow the recommended actions.
                        </p>
                    </div>

                    <div className="anomaly-page__button-group">
                        <ActionButton
                            label={isStarred ? "Starred" : "Mark as Starred"}
                            icon={<GoStar />}
                            primary={!isStarred}
                            completed={isStarred}
                            onClick={handleStar}
                        />
                        <ActionButton
                            label={isCompleted ? "Completed" : "Mark as Completed"}
                            icon={<GoCheckCircle />}
                            primary={!isCompleted}
                            completed={isCompleted}
                            onClick={handleComplete}
                        />
                    </div>
                </div>

                <div className="anomaly-page__main-grid">
                    <div className="anomaly-page__left-column">
                        <SectionBox title="Root Cause">
                            <p>{data.root_cause || "Root Cause Unknown."}</p>
                        </SectionBox>

                        <SectionBox title="Operation Impact">
                            <p>{data.operations || "Operation Impact Unknown."}</p>
                        </SectionBox>

                        <SectionBox
                            title="Recommended Action"
                            rightSlot={
                                recommendedAction ? (
                                    <span className="recommended-action-badge">Actionable</span>
                                ) : null
                            }
                        >
                            <p className="recommended-action-text">
                                {recommendedAction || "Recommended Action Unknown."}
                            </p>
                        </SectionBox>
                    </div>

                    <div className="anomaly-page__right-column">
                        <SectionBox title="Details">
                            <div className="detail-list">
                                <div className="detail-row">
                                    <p><strong>ATM / Server:</strong></p>
                                    <p>{data.ATM_ID ?? dbAnomaly?.atm_id ?? "SERVER"}</p>
                                </div>
                                <div className="detail-row">
                                    <p><strong>Severity:</strong></p>
                                    <p><span className="anomaly-status-pill">{data.Severity || "Unknown"}</span></p>
                                </div>
                                <div className="detail-row">
                                    <p><strong>Time Received:</strong></p>
                                    <p>{formatEventTime(data.Event_Time) || "Time Unknown"}</p>
                                </div>
                                {dbAnomaly?.correlation_id && (
                                    <div className="detail-row">
                                        <p><strong>Correlation ID:</strong></p>
                                        <p className="correlation-id">{dbAnomaly.correlation_id}</p>
                                    </div>
                                )}
                            </div>
                        </SectionBox>

                        <SectionBox title="Detection">
                            <ConfidenceBar score={confidence} />
                            <SourcesChips sources={sources} />
                        </SectionBox>
                    </div>
                </div>
            </div>
        </div>
    );
}

export default AnomalyData;
