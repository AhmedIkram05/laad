/* Import Libraries */
import { useParams } from "react-router-dom";
import { useEffect, useState } from "react";
import { GoStar, GoCheckCircle, GoInfo } from "react-icons/go";

/* Import Styles */
import "./AnomalyData.css";

/* Other Imports */
import { fetchDetailedAnalysis} from "../api/api";



  //////////////////////////////////////////////////////
  //////////   NOTE: THIS HAS BEEN STRIPPED   //////////
  //////////   BACK TO DATA THAT WILL BE      //////////
  //////////   RECEIVED FROM ANALYSIS         //////////
  //////////////////////////////////////////////////////



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

function ActionButton({ label, primary = false, icon, onClick }) {
  return (
    <button
      onClick={onClick}
      className={`anomaly-action-button ${
        primary
          ? "anomaly-action-button--primary"
          : "anomaly-action-button--secondary"
      }`}
    >
      {icon && <span className="buttonIcon">{icon}</span>}
      <span>{label}</span>
    </button>
  );
}



function AnomalyData() {
  const { anomaly_type } = useParams();
  const [data, setData] = useState(null);

  useEffect(() => {
    const load = async () => {
      try {
        const res = await fetchDetailedAnalysis(anomaly_type);

        const selected = res.data.find(
          (item) => item.Anomaly === anomaly_type
        );

      setData(selected || res.data[0]);
      } catch (err) {
        console.error("Failed to fetch analysis", err);
      }
    };

  load();
}, [anomaly_type]);

  if (!data) return <p>Loading...</p>;



  const handleStar = () => {
    alert("Star toggled (mock)");
  };

  const handleResolve = () => {
    alert("Marked as completed (mock)");
  };

  return (

    <div className="anomaly-page">
      <div className="anomaly-page__inner">

        {/* Title and Subtitle */}
        <div className="anomaly-page__header">
          <div>
            <h1 className="anomaly-page__title">{data.Title || "Title Unknown"}</h1>
            <p className="anomaly-page__subtitle">
              Review analysis, understand the ATM issue, and track the
              recommended next steps.
            </p>
          </div>

          {/* Mark as... Buttons */}
          <div className="anomaly-page__button-group">
            <ActionButton
              label="Mark as Starred"
              icon={<GoStar />}
              onClick={handleStar}
            />
            <ActionButton
              label="Mark as Completed"
              icon={<GoCheckCircle />}
              primary
              onClick={handleResolve}
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
            <SectionBox
              title="ATM Issue"
              rightSlot={
                <div className="anomaly-info-badge">
                  <GoInfo size={16} />
                </div>
              }
            >
              <p><strong>ATM:</strong> {data.ATM_ID || "ATM ID Unknown."}</p>
              <p><strong>Severity:</strong> {data.Severity || "Severity Unknown."}</p>
              <p><strong>Time:</strong> {data.Event_Time || "Time Unknown."}</p>
            </SectionBox>
          </div>
        </div>
      </div>
    </div>
  );
}

export default AnomalyData;