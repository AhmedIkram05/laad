/* Import Libraries */
import { useState, useEffect } from "react";
import { GoIssueDraft } from "react-icons/go";

/* Import Components + Styles */
import SearchBar from "../components/SearchBar";
import AnomalyCard from "../components/AnomalyCard";
import "./AnomalyListPage.css";

/* Other Imports */
import { fetchAnomalies, toggleStar } from "../api/api";



function AnomalyListPage({ title, filter, isActive = 1 }) {
  const [search, setSearch] = useState("");            // Search User Input Text
  const [filterBy, setFilterBy] = useState("title");   // Filter Field
  const [anomalies, setAnomalies] = useState([]);      // Grouped Anomaly Data
  const [loading, setLoading] = useState(true);        // Loading Indicator
  const [total, setTotal] = useState(0);               // Anomaly Count


  useEffect(() => {
    // Fetch Anomaly Data
    const load = async () => {
      try {
        const json = await fetchAnomalies(isActive);

        // Filter Data for Specific Page
        const filtered = filter ? json.data.filter(filter) : json.data;

        setAnomalies(filtered);
        setTotal(json.total);
      } catch (err) {
        console.error("Failed to fetch anomalies.", err);
      } finally {
        setLoading(false);
      }
    };
    load();
  }, [filter]);


  // Handle Toggling Starred
  const handleStar = async (id) => {
    try {
      await toggleStar(id);
      setAnomalies((prev) =>
        prev.map((a) =>
          a.representative_id === id
            ? { ...a, is_starred: !a.is_starred } : a
        )
      );
    } catch (err) {
      console.error("Failed to star anomaly.", err);
    }
  };


  // Calculate Time Updated
  const formatTime = (timestamp) => {
    const diff = Math.floor((Date.now() - new Date(timestamp)) / 60000);
    if (diff < 1) return "Just now";
    if (diff < 60) return `${diff} mins ago`;
    const hours = Math.floor(diff / 60);
    return `${hours} hrs ago`;
  };


  // Search Bar Logic
  const searchedAnomalies = anomalies.filter((a) => {
    const value = String(a[filterBy] ?? "").toLowerCase();
    return value.includes(search.toLowerCase());
  });


  return (
    <>

      {/* Search and Filter Bar */}
      <SearchBar search={search} setSearch={setSearch} filterBy={filterBy} setFilterBy={setFilterBy} />

      {/* Main Page Content */}
      <div className="mainContainer">
 
        {/* Title and Count */}
        <div className="titleContainer">
          <h1>{title}</h1>
          <h2>({total})</h2>
        </div>

        {/* Anomaly Cards (and Loading) */}
        <div className="anomalyContainer">
          {loading ? (
            <div className="loadingContainer">
              <p>Loading anomalies...</p>
              <div className="loadingIcon"><GoIssueDraft /></div>
            </div>
          ) : searchedAnomalies.length === 0 ? (
            <div className="noAnomaliesFound"><p>No anomalies found.</p></div>
          ) : (
            searchedAnomalies.map((a) => (
              <AnomalyCard
                key={a.group_id}
                id={a.representative_id}
                title={a.title || "Title Unknown"}
                atm_id={a.atm_id || "ATM ID Unknown"}
                severity={a.representative_severity || "Severity Unknown"}
                update_time={formatTime(a.latest_detected_at)}
                anomaly_type={a.anomaly_type}
                is_starred={a.is_starred}
                toggle_star={() => handleStar(a.representative_id)}
              />
            ))
          )}
        </div>

      </div>

    </>
  );
}


export default AnomalyListPage;