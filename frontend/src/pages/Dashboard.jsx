/* Import Components */
import AnomalyCard from "../components/AnomalyCard";

/* Import Styles */
import './Dashboard.css'


function Dashboard() {
  return (
    <>

      {/* Search and Filter Bar */}
      <div className="searchContainer">
        <p>Search Bar</p>
      </div>

      {/* Main Page Content */}
      <div className="mainContainer">
 
        {/* Title and Count */}
        <div className="titleContainer">
          <h1>Anomalies Detected</h1>
          <h2>[count]</h2>
        </div>

        {/* Example Anomaly Cards */}
        <div className="anomalyContainer">
          <AnomalyCard
            title="Cassette Empty"
            atmID="ATM-GB-0003"
            count="4 anomalies"
            updatedTime="Updated: 2 mins ago"
          />

          <AnomalyCard
            title="Cash Jam Detected"
            atmID="ATM-GB-0007"
            count="2 anomalies"
            updatedTime="Updated: 5 mins ago"
          />

          <AnomalyCard
            title="Memory Spike"
            atmID="ATM-GB-0005"
            count="6 anomalies"
            updatedTime="Updated: 11 mins ago"
          />

          <AnomalyCard
            title="Cassette Empty"
            atmID="ATM-GB-0002"
            count="5 anomalies"
            updatedTime="Updated: 24 mins ago"
          />

          <AnomalyCard
            title="Cash Jam Detected"
            atmID="ATM-GB-0013"
            count="1 anomaly"
            updatedTime="Updated: 37 mins ago"
          />
        </div>

      </div>

    </>
  );
}


export default Dashboard;