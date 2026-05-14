/*
 * AnomalyCard Component
 * --------------------
 * Handles the display of details for a singular anomaly.
 */

// External Libraries
import { useNavigate } from "react-router-dom";
import { GoAlert, GoCheckCircle, GoCircle } from "react-icons/go";

/* Internal Imports */
import StarIcon from "../components/StarIcon";
import { toggleComplete } from "../api/api";
import "./AnomalyCard.css";

function AnomalyCard({ id, title, atm_id, severity, update_time, anomaly_type, is_starred, is_active, toggle_star, onCompleted }) {
    const navigate = useNavigate();

    const handleComplete = async () => {
        try {
            await toggleComplete(id);
            if (onCompleted) onCompleted(id);
        } catch (err) {
            console.error("Failed to resolve anomaly", err);
        }
    };

    return (

        <div className="card">
            <div className="body">
                {/* Title */}
                <div className="title">
                    <div className="alertIcon"><GoAlert /></div>
                    <h3 className="anomalyCardTitle">{title}</h3>
                </div>

                {/* ATM ID, Severity, Updated Time */}
                <div className="details">
                    <p>{atm_id}</p>
                    <div className="updates">
                        <p>{severity}</p>
                        <p>Received: {update_time}</p>
                    </div>
                </div>
            </div>

            {/* View Button, Starred State, Completed Button */}
            <div className="buttons">
                <button className="view" onClick={() => navigate(`/data/${anomaly_type}`, { state: { anomaly_type }, }) }>View</button>
                <StarIcon id={id} isStarred={is_starred} toggleStar={toggle_star} />
                <button
                    className={`completeBtn ${is_active === 0 ? "completeBtn--done" : ""}`}
                    onClick={handleComplete}
                    title={is_active === 0 ? "Mark as unresolved" : "Mark as resolved"}
                >
                    {is_active === 0 ? <GoCheckCircle /> : <GoCircle />}
                </button>
          </div>
        </div>
    );
}

export default AnomalyCard;