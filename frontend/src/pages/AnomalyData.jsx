/* Import Libraries */
import { useParams } from "react-router-dom";
import { useEffect, useState } from "react";
import { GoStar, GoCheckCircle } from "react-icons/go";

/* Import Components + Styles */
import BackButton from "../components/BackButton";
import "./AnomalyData.css";

/* Other Imports */
import { fetchAnomalies, fetchDetailedAnalysis, toggleComplete, toggleStar } from "../api/api";


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

    const handleComplete = async () => {
        if (!data) return;
        try {
            await toggleComplete(data.id);
            setIsCompleted(prev => !prev);
        } catch (err) {
            console.error("Failed to resolve anomaly", err);
        }
    };

    const handleStar = async () => {
        if (!data) return;
        try {
            await toggleStar(data.id);
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
                    fetchAnomalies()
                ]);

                const selectedAnalysis = analysisRes.data.find(
                    (item) => item.Anomaly === anomaly_type
                );

                const analysis = selectedAnalysis || analysisRes.data[0];

                const matchedAnomaly = anomaliesRes.data.find(
                    (a) => a.anomaly_type === anomaly_type
                );

                setData(analysis);

                if (matchedAnomaly) {
                    setIsStarred(matchedAnomaly.is_starred === 1);
                    setIsCompleted(matchedAnomaly.is_active === 0);
                }

            } catch (err) {
                console.error("Failed to fetch data", err);
            }
        };

        load();
    }, [anomaly_type]);

    if (!data) return <p>Loading...</p>;


    return (
        <div className="anomaly-page">
            <div className="anomaly-page__inner">

                {/* Back Button */}
                <div className="anomaly-page__header">
                    <div className="back-button-container"><BackButton/></div>

                    {/* Title and Subtitle */}
                    <div className="anomaly-page__text">
                        <h1 className="anomaly-page__title">{data.Title || "Title Unknown"}</h1>
                        <p className="anomaly-page__subtitle">Review analysis, understand the ATM issue, and track the recommended next steps.
                        </p>
                    </div>

                    {/* Mark as... Buttons */}
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

                {/* Root Cause + Impact + Recommended Action */}
                <div className="anomaly-page__main-grid">
                    <div className="anomaly-page__left-column">
                        <SectionBox title="Root Cause">
                            <p>{data.root_cause || "Root Cause Unknown."}</p>
                        </SectionBox>

                        <SectionBox title="Operation Impact">
                            <p>{data.operations || "Operation Impact Unknown."}</p>
                        </SectionBox>

                        <SectionBox title="Recommended Action">
                            <p>{data.Recommended_Action || "Recommended Action Unknown."}</p>
                        </SectionBox>
                    </div>

                    {/* ATM Details */}
                    <div className="anomaly-page__right-column">
                        <SectionBox title="Details">
                            <div className="detail-list">
                                <div className="detail-row">
                                    <p><strong>ATM:</strong></p>
                                    <p>{data.ATM_ID || "N/A"}</p>
                                </div>
                                <div className="detail-row">
                                    <p><strong>Severity:</strong></p>
                                    <p><div className="anomaly-status-pill">{data.Severity || "Severity Unknown"}</div></p>
                                </div>
                                <div className="detail-row">
                                    <p><strong>Time Received:</strong></p>
                                    <p>{formatEventTime(data.Event_Time) || "Time Unknown"}</p>
                                </div>
                            </div>
                        </SectionBox>
                    </div>
                </div>
            </div>
        </div>
    );
}

export default AnomalyData;