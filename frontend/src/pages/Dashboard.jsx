/* Import Libraries */
import { useState } from "react";

/* Import Components */
import SearchBar from "../components/SearchBar";
import AnomalyCard from "../components/AnomalyCard";

/* Import Styles */
import './Dashboard.css'


function Dashboard() {
  const [search, setSearch] = useState("");
  const [filterBy, setFilterBy] = useState("title");

  const anomalyList = [
    {title: "Cassette Empty", ID: "ATM-GB-0003", count: 4, updatedTime: "2 mins ago"},
    {title: "Cash Jam Detected", ID: "ATM-GB-0007", count: 2, updatedTime: "5 mins ago"},
    {title: "Memory Spike", ID: "ATM-GB-0005", count: 6, updatedTime: "11 mins ago"},
    {title: "Cassette Empty", ID: "ATM-GB-0002", count: 5, updatedTime: "24 mins ago"},
    {title: "Cash Jam Detected", ID: "ATM-GB-0013", count: 1, updatedTime: "37 mins ago"}
  ];

  const searchedAnomalies = anomalyList.filter((a) => {
    const value = a[filterBy];
    return value.toLowerCase().includes(search.toLowerCase());
  });


  return (
    <>
      {/* Search and Filter Bar */}
      <SearchBar search={search} setSearch={setSearch} filterBy={filterBy} setFilterBy={setFilterBy} />

      {/* Main Page Content */}
      <div className="mainContainer">
 
        {/* Title and Count */}
        <div className="titleContainer">
          <h1>Anomalies Detected</h1>
          <h2>({searchedAnomalies.length})</h2>
        </div>

        {/* Anomaly Cards */}
        <div className="anomalyContainer">
          {searchedAnomalies.map((a, index) => (
            <AnomalyCard
              key={index}
              title={a.title}
              ID={a.ID}
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