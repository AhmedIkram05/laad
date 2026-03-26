/* Import Libraries */
import { useState } from "react";

/* Import Components */
import SearchBar from "../components/SearchBar";
import AnomalyCard from "../components/AnomalyCard";

/* Import Styles */
import './Dashboard.css'


function Dashboard() {
  const [search, setSearch] = useState("");

  const anomalyList = [
    {title: "Cassette Empty", atmID: "ATM-GB-0003", count: 4, updatedTime: "2 mins ago"},
    {title: "Cash Jam Detected", atmID: "ATM-GB-0007", count: 2, updatedTime: "5 mins ago"},
    {title: "Memory Spike", atmID: "ATM-GB-0005", count: 6, updatedTime: "11 mins ago"},
    {title: "Cassette Empty", atmID: "ATM-GB-0002", count: 5, updatedTime: "24 mins ago"},
    {title: "Cash Jam Detected", atmID: "ATM-GB-0013", count: 1, updatedTime: "37 mins ago"}
  ];

  const searchedAnomalies = anomalyList.filter((a) =>
    a.title.toLowerCase().includes(search.toLowerCase())
  );


  return (
    <>
      {/* Search Bar - work in progress */}
      <SearchBar search={search} setSearch={setSearch} />

      {/* Main Page Content */}
      <div className="mainContainer">
 
        {/* Title and Count */}
        <div className="titleContainer">
          <h1>Anomalies Detected</h1>
          <h2>{searchedAnomalies.length}</h2>
        </div>

        {/* Anomaly Cards */}
        <div className="anomalyContainer">
          {searchedAnomalies.map((a, index) => (
            <AnomalyCard
              key={index}
              title={a.title}
              atmID={a.atmID}
              count={`${a.count} ${a.count === 1 ? "anomaly" : "anomalies"}`}
              updatedTime={`Updated: ${a.updatedTime}`}
            />
          ))}
        </div>

      </div>

    </>
  );
}


export default Dashboard;