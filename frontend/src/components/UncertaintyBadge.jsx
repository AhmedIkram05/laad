/*
 * UncertaintyBadge Component
 * --------------------
 * Displays confidence level indicator with score.
 */

import "./UncertaintyBadge.css";

function UncertaintyBadge({level, score}) {
    const getLevelColor = () => {
        switch (level) {
            case "high":
                return "#10b981";
            case "medium":
                return "#f59e0b";
            case "low":
                return "#ef4444";
            default:
                return "#6b7280";
        }
    };

    const getLevelIcon = () => {
        switch (level) {
            case "high":
                return "✓";
            case "medium":
                return "⚠";
            case "low":
                return "✗";
            default:
                return "?";
        }
    };

    return (
        <div className="uncertainty-badge">
            <span
                className="badge-indicator"
                style={{backgroundColor: getLevelColor()}}
            >
                {getLevelIcon()}
            </span>
            <span className="badge-text">
                <span className="confidence-level" style={{color: getLevelColor()}}>
                    {level.charAt(0).toUpperCase() + level.slice(1)} Confidence
                </span>
                <span className="confidence-score">
                    {(score * 100).toFixed(0)}%
                </span>
            </span>
        </div>
    );
}

export default UncertaintyBadge;