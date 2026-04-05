/*
 * AnomalyListPage Component
 * --------------------
 * Handles the display of a filtered list of anomalies.
 */

/* External Libraries */
import { useState, useEffect } from "react";
import { GoIssueDraft } from "react-icons/go";

/* Internal Imports */
import SearchBar from "../components/SearchBar";
import AnomalyCard from "../components/AnomalyCard";
import { fetchAnomalies, fetchDetailedAnalysis, toggleStar } from "../api/api";
import "./AnomalyListPage.css";

function AnomalyListPage({ title, subtitle, filter, isActive = 1 }) {
    const [search, setSearch] = useState(""); // Search User Input Text
    const [filterBy, setFilterBy] = useState("title"); // Filter Field
    const [anomalies, setAnomalies] = useState([]); // Grouped Anomaly Data
    const [loading, setLoading] = useState(true); // Loading Indicator

    useEffect(() => {
        // Fetch and Process Anomaly and Analysis Data
        const load = async () => {
            try {
                const [anomalyRes, analysisRes] = await Promise.all([fetchAnomalies(isActive), fetchDetailedAnalysis()]);
                let anomaliesData = anomalyRes.data;
                const analysisData = analysisRes.data;

                // (Optional) Filter Data for Specific Page
                if (filter) {
                    anomaliesData = anomaliesData.filter(filter);
                }

                // Order Anomalies by Analysis Algorithm
                const orderMap = {};
                analysisData.forEach((item, index) => {
                    orderMap[item.Anomaly] = index;
                });
                const sorted = [...anomaliesData].sort((a, b) => {
                    const orderA = orderMap[a.anomaly_type] ?? Infinity;
                    const orderB = orderMap[b.anomaly_type] ?? Infinity;
                    return orderA - orderB;
                });

                setAnomalies(sorted);
            } catch (err) {
                console.error("Failed to fetch anomalies.", err);
            } finally {
                setLoading(false);
            }
        };
        load();
    }, [filter, isActive]);

    /*
     * Toggles the "Starred" state if an anomaly
     *
     * @param id - the anomaly ID
     */
    const handleStar = async (id) => {
        try {
            await toggleStar(id);
            setAnomalies((prev) => prev.map((a) => (a.id === id ? { ...a, is_starred: !a.is_starred } : a)));
        } catch (err) {
            console.error("Failed to star anomaly.", err);
        }
    };

    /*
     * Converts timestamp into an easily readable format
     *
     * @param timestamp - the timestamp to format
     * @returns {string} - formatted time
     */
    const formatTime = (timestamp) => {
        const diff = Math.floor((Date.now() - new Date(timestamp)) / 60000);
        if (diff < 1) return "Just now";
        if (diff < 60) return `${diff} mins ago`;
        const hours = Math.floor(diff / 60);
        return `${hours} hrs ago`;
    };

    // Filters anomalies based on search input
    const searchedAnomalies = anomalies.filter((a) => {
        const value = String(a[filterBy] ?? "").toLowerCase();
        return value.includes(search.toLowerCase());
    });

    return (
        <>
            {/* Main Page Content */}
            <div className="mainContainer">
                {/* Title and Count */}
                <div className="titleContainer">
                    <h1>{title}</h1>
                    <h2>({searchedAnomalies.length})</h2>
                </div>

                {/* Subtitle */}
                <p className="subtitleContainer">{subtitle ?? "Detected anomalies across ATM and server systems, prioritised by severity."}</p>

                {/* Search and Filter Bar */}
                <SearchBar search={search} setSearch={setSearch} filterBy={filterBy} setFilterBy={setFilterBy} />

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
                        searchedAnomalies.map((a) => <AnomalyCard key={a.id} id={a.id} title={a.title || "Title Unknown"} atm_id={a.atm_id ?? "SERVER"} severity={a.severity || "Severity Unknown"} anomaly_type={a.anomaly_type} update_time={formatTime(a.detected_at)} is_starred={a.is_starred} toggle_star={() => handleStar(a.id)} />)
                    )}
                </div>
            </div>
        </>
    );
}

export default AnomalyListPage;