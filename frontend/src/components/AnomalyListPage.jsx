/*
 * AnomalyListPage Component
 * --------------------
 * Handles the display of a filtered list of anomalies.
 */

/* External Libraries */
import { useState, useEffect, useCallback } from "react";
import { GoIssueDraft } from "react-icons/go";

/* Internal Imports */
import SearchBar from "../components/SearchBar";
import AnomalyCard from "../components/AnomalyCard";
import { fetchAnomalies, fetchDetailedAnalysis, toggleStar, fetchMetrics } from "../api/api";
import "./AnomalyListPage.css";

function AnomalyListPage({ title, subtitle, filter, isActive = 1, showMetrics = false }) {
    const [search, setSearch] = useState("");
    const [anomalies, setAnomalies] = useState([]);
    const [loading, setLoading] = useState(true);
    const [metrics, setMetrics] = useState(null);
    const [timeFilter, setTimeFilter] = useState("24h");
    const [logStream, setLogStream] = useState([]);
    const [logSearch, setLogSearch] = useState("");
    const [now, setNow] = useState(() => Date.now());
    const [sortBy, setSortBy] = useState("score");
    const [detectionSource, setDetectionSource] = useState("");
    const [atmIdFilter, setAtmIdFilter] = useState("");
    const [anomalyTypeFilter, setAnomalyTypeFilter] = useState("");
    const [severityFilter, setSeverityFilter] = useState("");

    const hours = timeFilter === "1h" ? 1 : timeFilter === "6h" ? 6 : timeFilter === "7d" ? 168 : 24;
    const bucket = timeFilter === "1h" ? 5 : timeFilter === "6h" ? 30 : timeFilter === "7d" ? 360 : 60;

    const loadMetrics = useCallback(async () => {
        try {
            const res = await fetchMetrics(hours, bucket);
            setMetrics(res);
        } catch (err) {
            console.error("Failed to fetch metrics", err);
        }
    }, [hours, bucket]);

    const loadLogStream = useCallback(async () => {
        try {
            const ds = detectionSource || null;
            const res = await fetchAnomalies(null, hours, sortBy, ds, null, atmIdFilter || null, anomalyTypeFilter || null, severityFilter || null);
            setLogStream(res.data || []);
        } catch (err) {
            console.error("Failed to fetch log stream", err);
        }
    }, [hours, sortBy, detectionSource, atmIdFilter, anomalyTypeFilter, severityFilter]);

useEffect(() => {
        let cancelled = false;
        const load = async () => {
            try {
                const ds = detectionSource || null;
                const anomalyRes = await fetchAnomalies(isActive, hours, sortBy, ds, null, atmIdFilter || null, anomalyTypeFilter || null, severityFilter || null);
                if (cancelled) return;
                let anomaliesData = anomalyRes.data;

                if (filter) {
                    anomaliesData = anomaliesData.filter(filter);
                }

                setAnomalies(anomaliesData);
            } catch (err) {
                console.error("Failed to fetch anomalies.", err);
            } finally {
                if (!cancelled) setLoading(false);
            }
        };
        load();

        if (showMetrics) {
            // eslint-disable-next-line react-hooks/set-state-in-effect -- Data fetching on dep change is a legitimate useEffect use case
            loadMetrics();
            loadLogStream();
        }

        return () => { cancelled = true; };
    }, [filter, isActive, showMetrics, hours, loadMetrics, loadLogStream, sortBy, detectionSource, atmIdFilter, anomalyTypeFilter, severityFilter]);

    // Tick every 30s to refresh relative timestamps
    useEffect(() => {
        const timer = setInterval(() => setNow(Date.now()), 30_000);
        return () => clearInterval(timer);
    }, []);

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

    const handleCompleted = (id) => {
        setAnomalies((prev) => prev.map((a) => (a.id === id ? { ...a, is_active: a.is_active === 0 ? 1 : 0 } : a)));
    };

    /*
     * Converts timestamp into an easily readable format
     *
     * @param timestamp - the timestamp to format
     * @returns {string} - formatted time
     */
    const formatTime = (timestamp) => {
        const diff = Math.floor((now - new Date(timestamp)) / 60000);
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

    // Time range options
    const timeOptions = [
        { value: "1h", label: "1h" },
        { value: "6h", label: "6h" },
        { value: "24h", label: "24h" },
        { value: "7d", label: "7d" },
    ];

    // Option C: Log stream filtering
    const filteredLogs = logStream.filter((a) => {
        if (!logSearch) return true;
        const q = logSearch.toLowerCase();
        return (a.title || "").toLowerCase().includes(q) ||
               (a.anomaly_type || "").toLowerCase().includes(q) ||
               (a.atm_id || "").toLowerCase().includes(q) ||
               (a.severity || "").toLowerCase().includes(q);
    });

    const anomalyTypeCounts = anomalies.reduce((acc, a) => {
        acc[a.anomaly_type] = (acc[a.anomaly_type] || 0) + 1;
        return acc;
    }, {});

    return (
        <>
            {/* Main Page Content */}
            <div className="mainContainer">
                {/* Option B: Metrics Dashboard Cards */}
                {showMetrics && metrics && (
                    <div className="metricsDashboard">
                        <div className="metricsGrid">
                            <div className="metricCard metricCard--total">
                                <span className="metricCard__value">{metrics.summary.total}</span>
                                <span className="metricCard__label">Total</span>
                            </div>
                            <div className="metricCard metricCard--active">
                                <span className="metricCard__value">{metrics.summary.active}</span>
                                <span className="metricCard__label">Active</span>
                            </div>
                            <div className="metricCard metricCard--resolved">
                                <span className="metricCard__value">{metrics.summary.resolved}</span>
                                <span className="metricCard__label">Resolved</span>
                            </div>
                            <div className="metricCard metricCard--critical">
                                <span className="metricCard__value">{metrics.summary.critical}</span>
                                <span className="metricCard__label">Critical</span>
                            </div>
                            <div className="metricCard metricCard--major">
                                <span className="metricCard__value">{metrics.summary.major}</span>
                                <span className="metricCard__label">Major</span>
                            </div>
                            <div className="metricCard metricCard--high">
                                <span className="metricCard__value">{metrics.summary.high}</span>
                                <span className="metricCard__label">High</span>
                            </div>
                        </div>

                        {/* Option A: Timeline - simple bar representation */}
                        <div className="timelineSection">
                            <div className="timelineHeader">
                                <h3>Anomaly Timeline</h3>
                                <div className="timeFilterGroup">
                                    {timeOptions.map((opt) => (
                                        <button
                                            key={opt.value}
                                            className={`timeFilterBtn ${timeFilter === opt.value ? "timeFilterBtn--active" : ""}`}
                                            onClick={() => setTimeFilter(opt.value)}
                                        >
                                            {opt.label}
                                        </button>
                                    ))}
                                </div>
                            </div>
                            <div className="timelineBars">
                                {metrics.time_series && metrics.time_series.length > 0 ? (
                                    metrics.time_series.map((bucket, i) => {
                                        const maxTotal = Math.max(...metrics.time_series.map((b) => b.total), 1);
                                        const heightPct = (bucket.total / maxTotal) * 100;
                                        const types = bucket.types || {};
                                        return (
                                            <div key={i} className="timelineBar" style={{ height: `${Math.max(heightPct, 4)}%` }} title={`${bucket.total} anomalies at ${bucket.bucket_start || ""}`}>
                                                <span className="timelineBar__count">{bucket.total}</span>
                                                <div className="timelineBar__fill" style={{ height: `${heightPct}%` }}>
                                                    {Object.entries(types).map(([type, count]) => (
                                                        <div
                                                            key={type}
                                                            className="timelineBar__segment"
                                                            style={{
                                                                height: `${(count / Math.max(bucket.total, 1)) * 100}%`,
                                                                backgroundColor: SEVERITY_COLORS[type] || "#6b7280",
                                                            }}
                                                        />
                                                    ))}
                                                </div>
                                            </div>
                                        );
                                    })
                                ) : (
                                    <p className="noData">No anomaly data for this time period.</p>
                                )}
                            </div>
                        </div>

                        {/* Option B: Type Distribution */}
                        <div className="typeDistribution">
                            <h3>By Type</h3>
                            <div className="typeBadgeGrid">
                                {Object.entries(anomalyTypeCounts).sort().map(([type, count]) => (
                                    <div key={type} className="typeBadge" style={{ borderColor: SEVERITY_COLORS[type] || "#6b7280" }}>
                                        <span className="typeBadge__type">{type}</span>
                                        <span className="typeBadge__count">{count}</span>
                                    </div>
                                ))}
                            </div>
                        </div>
                    </div>
                )}

                {/* Title and Count */}
                <div className="titleContainer">
                    <h1>{title}</h1>
                    <h2>({searchedAnomalies.length})</h2>
                </div>

                {/* Subtitle */}
                <p className="subtitleContainer">{subtitle ?? "Detected anomalies across ATM and server systems, prioritised by severity."}</p>

                {/* Search and Filter Bar */}
                <SearchBar search={search} setSearch={setSearch} />

                {/* Advanced Filters and Sort */}
                <div className="filterControls">
                    <div className="filterGroup">
                        <label>Sort by:</label>
                        <select value={sortBy} onChange={(e) => setSortBy(e.target.value)}>
                            <option value="score">Criticality Score</option>
                            <option value="detected_at">Most Recent</option>
                            <option value="severity">Severity</option>
                        </select>
                    </div>
                    <div className="filterGroup">
                        <label>Detection Source:</label>
                        <select value={detectionSource} onChange={(e) => setDetectionSource(e.target.value)}>
                            <option value="">All Sources</option>
                            <option value="CLASSIFIER">CLASSIFIER</option>
                            <option value="ZSCORE">ZSCORE</option>
                            <option value="SIGNAL_CORRELATOR">SIGNAL_CORRELATOR</option>
                        </select>
                    </div>
                    <div className="filterGroup">
                        <label>ATM ID:</label>
                        <select value={atmIdFilter} onChange={(e) => setAtmIdFilter(e.target.value)}>
                            <option value="">All ATMs</option>
                            <option value="ATM-GB-0001">ATM-GB-0001</option>
                            <option value="ATM-GB-0002">ATM-GB-0002</option>
                            <option value="ATM-GB-0003">ATM-GB-0003</option>
                            <option value="ATM-GB-0004">ATM-GB-0004</option>
                            <option value="ATM-GB-0005">ATM-GB-0005</option>
                            <option value="ATM-GB-0006">ATM-GB-0006</option>
                            <option value="ATM-GB-0007">ATM-GB-0007</option>
                            <option value="ATM-GB-0008">ATM-GB-0008</option>
                            <option value="ATM-GB-0009">ATM-GB-0009</option>
                            <option value="ATM-GB-0010">ATM-GB-0010</option>
                        </select>
                    </div>
                    <div className="filterGroup">
                        <label>Anomaly Type:</label>
                        <select value={anomalyTypeFilter} onChange={(e) => setAnomalyTypeFilter(e.target.value)}>
                            <option value="">All Types</option>
                            <option value="A1">A1 - Network Timeout</option>
                            <option value="A2">A2 - Cash Cassette Empty</option>
                            <option value="A3">A3 - JVM Memory Leak</option>
                            <option value="A4">A4 - Container Restart</option>
                            <option value="A5">A5 - Response Time Spike</option>
                            <option value="A6">A6 - OS Memory Pressure</option>
                            <option value="A7">A7 - Out-of-Order</option>
                            <option value="UNKNOWN">UNKNOWN</option>
                        </select>
                    </div>
                    <div className="filterGroup">
                        <label>Severity:</label>
                        <select value={severityFilter} onChange={(e) => setSeverityFilter(e.target.value)}>
                            <option value="">All Severities</option>
                            <option value="CRITICAL">CRITICAL</option>
                            <option value="HIGH">HIGH</option>
                            <option value="MAJOR">MAJOR</option>
                            <option value="LOW">LOW</option>
                        </select>
                    </div>
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
                        searchedAnomalies.map((a) => <AnomalyCard key={a.id} id={a.id} title={a.title || "Title Unknown"} atm_id={a.atm_id ?? "SERVER"} severity={a.severity || "Severity Unknown"} anomaly_type={a.anomaly_type} update_time={formatTime(a.detected_at)} is_starred={a.is_starred} is_active={a.is_active} toggle_star={() => handleStar(a.id)} onCompleted={handleCompleted} />)
                    )}
                </div>

                {/* Option C: Log Stream */}
                {showMetrics && (
                    <div className="logStreamSection">
                        <h3>Event Log Stream</h3>
                        <input
                            type="text"
                            className="logStreamSearch"
                            placeholder="Search logs by title, type, ATM ID, or severity..."
                            value={logSearch}
                            onChange={(e) => setLogSearch(e.target.value)}
                        />
                        <div className="logStreamList">
                            {filteredLogs.length === 0 ? (
                                <p className="noData">No log entries match your search.</p>
                            ) : (
                                filteredLogs.slice(0, 50).map((a) => (
                                    <div key={a.id} className={`logStreamRow ${a.anomaly_type ? "logStreamRow--anomaly" : "logStreamRow--normal"}`}>
                                        <span className={`logStreamRow__tag ${a.is_active === 0 ? "logStreamRow__tag--resolved" : ""}`}>
                                            {a.anomaly_type || "NORMAL"}
                                        </span>
                                        <span className="logStreamRow__title">{a.title || "Event"}</span>
                                        <span className="logStreamRow__meta">
                                            {a.atm_id || ""} &middot; {a.severity || ""} &middot; {formatTime(a.detected_at)}
                                        </span>
                                    </div>
                                ))
                            )}
                        </div>
                    </div>
                )}
            </div>
        </>
    );
}

const SEVERITY_COLORS = {
    A1: "#dc2626", A2: "#dc2626", A3: "#d97706",
    A4: "#d97706", A5: "#d97706", A6: "#d97706", A7: "#2563eb",
    UNKNOWN: "#6b7280",
    CRITICAL: "#dc2626", MAJOR: "#d97706", HIGH: "#2563eb",
};

export default AnomalyListPage;