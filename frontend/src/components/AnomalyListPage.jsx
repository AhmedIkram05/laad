
////////////////////////////////////////////////////////////////////////////////
/////      TEMPLATE FOR ANOMALY LIST PAGES, RECEIVES A PAGE AND FILTER     /////
/////      AND DISPLAYS RELEVANT ANOMALIES                                 /////
////////////////////////////////////////////////////////////////////////////////


/* Import Libraries */
import { useState, useEffect } from "react";
import { GoIssueDraft } from "react-icons/go";

/* Import Components + Styles */
import SearchBar from "../components/SearchBar";
import AnomalyCard from "../components/AnomalyCard";
import "./AnomalyListPage.css";

/* Other Imports */
import { fetchAnomalies, fetchDetailedAnalysis, toggleStar } from "../api/api";


function AnomalyListPage({ title, filter, isActive = 1 }) {
  const [search, setSearch] = useState(""); // Search User Input Text
  const [filterBy, setFilterBy] = useState("title"); // Filter Field
  const [anomalies, setAnomalies] = useState([]); // Grouped Anomaly Data
  const [loading, setLoading] = useState(true); // Loading Indicator


  useEffect(() => {
    // Fetch Anomaly Data: Uses GET /anomalies for data
    // and GET /detailed analysis for ordering
    const load = async () => {
      try {
        const [anomalyRes, analysisRes] = await Promise.all([
          fetchAnomalies(isActive),
          fetchDetailedAnalysis()
        ])
        let anomaliesData = anomalyRes.data;
        const analysisData = analysisRes.data;

        // Filter Data for Specific Page
        if (filter) {
          anomaliesData = anomaliesData.filter(filter);
        }

        // Order anomalies by analysis algorithm
        const orderMap = {};
        analysisData.forEach((item, index) => {
          orderMap[item.Anomaly] = index;
        });

        const sorted = [...anomaliesData].sort((a,b) => {
          const orderA = orderMap[a.anomaly_type] ?? Infinity;
          const orderB = orderMap[b.anomaly_type] ?? Infinity;
          return orderA - orderB;
        })

        setAnomalies(sorted);
      } catch (err) {
        console.error("Failed to fetch anomalies.", err);
      } finally {
        setLoading(false);
      }
    };
      load();
  }, [filter, isActive]);


  // Handle Toggling Starred
  const handleStar = async (id) => {
    try {
      await toggleStar(id);
      setAnomalies((prev) => prev.map((a) => (a.id === id ? { ...a, is_starred: !a.is_starred } : a)));
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
          <h2>({searchedAnomalies.length})</h2>
        </div>

        {/* Anomaly Cards (and Loading) */}
        <div className="anomalyContainer">
          {loading ? (
            <div className="loadingContainer">
              <p>Loading anomalies...</p>
              <div className="loadingIcon">
                <GoIssueDraft />
              </div>
            </div>
          ) : searchedAnomalies.length === 0 ? (
            <div className="noAnomaliesFound">
              <p>No anomalies found.</p>
            </div>
          ) : (
            searchedAnomalies.map((a) =>
              <AnomalyCard
                key={a.id}
                id={a.id}
                title={a.title || "Title Unknown"}
                atm_id={a.atm_id || "ATM: N/A"}
                severity={a.severity || "Severity Unknown"}
                anomaly_type={a.anomaly_type}
                update_time={formatTime(a.detected_at)}
                is_starred={a.is_starred}
                toggle_star={() => handleStar(a.id)}
              />
            )
          )}
        </div>
      </div>

    </>

  );
}

export default AnomalyListPage;