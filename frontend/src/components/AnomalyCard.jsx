
////////////////////////////////////////////////////////////////////////////////
/////      TEMPLATE FOR ANOMALY DETAIL CARDS DISPLAYED IN LISTS            /////
////////////////////////////////////////////////////////////////////////////////


/* Import Libraries */
import { useNavigate } from "react-router-dom";
import { GoAlert } from "react-icons/go";

/* Import Components + Styles */
import StarIcon from "../components/StarIcon";
import "./AnomalyCard.css";


function AnomalyCard({ id, title, atm_id, severity, update_time, anomaly_type, is_starred, toggle_star }) {
  const navigate = useNavigate();

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
            <p>Updated: {update_time}</p>
          </div>
        </div>

      </div>

      {/* View Button, Starred State */}
      <div className="buttons">
        <button className="view" onClick={() =>
          navigate(`/data/${anomaly_type}`, { state: { anomaly_type }, }) }>
          View
        </button>
        <StarIcon id={id} isStarred={is_starred} toggleStar={toggle_star} />
      </div>
          
    </div>

  );
}

export default AnomalyCard;