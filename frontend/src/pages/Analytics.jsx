import { useState, useEffect } from "react";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
  ReferenceDot
} from "recharts";
import { Activity, BarChart3, Settings } from "lucide-react";
import { getAuthHeaders } from "../api/api";
import "./Analytics.css";

const EVENT_SOURCES = ["ATM_APP", "HARDWARE", "TERMINAL_HANDLER"];
const METRIC_SOURCES = ["KAFKA", "PROMETHEUS", "OS", "CLOUD"];

const SOURCE_COLORS = {
  ATM_APP: "#10b981",
  HARDWARE: "#3b82f6",
  TERMINAL_HANDLER: "#8b5cf6",
  KAFKA: "#f59e0b",
  PROMETHEUS: "#ec4899",
  OS: "#06b6d4",
  CLOUD: "#6366f1"
};

function Analytics() {
  const [activeTab, setActiveTab] = useState("events");
  const [hours, setHours] = useState(24);
  const [bucketMinutes, setBucketMinutes] = useState(60);
  const [eventsData, setEventsData] = useState([]);
  const [metricsData, setMetricsData] = useState([]);
  const [loading, setLoading] = useState(false);
  const [selectedSources, setSelectedSources] = useState({
    ATM_APP: true,
    HARDWARE: true,
    TERMINAL_HANDLER: true,
    KAFKA: true,
    PROMETHEUS: true,
    OS: true,
    CLOUD: true
  });
  const [selectedMetric, setSelectedMetric] = useState("jvm_memory_used_bytes");

  const fetchEventsData = async () => {
    setLoading(true);
    try {
      const enabledSources = Object.entries(selectedSources)
        .filter(([_, v]) => v)
        .map(([k]) => k)
        .filter(s => EVENT_SOURCES.includes(s))
        .join(",");
      
      const res = await fetch(
        `/api/analytics/events?hours=${hours}&bucket_minutes=${bucketMinutes}${enabledSources ? `&sources=${enabledSources}` : ""}`,
        { headers: getAuthHeaders() }
      );
      const data = await res.json();
      if (data.time_series) {
        const processed = data.time_series.map(bucket => {
          const entry = { time: bucket.bucket_start };
          // Zero-fill all EVENT_SOURCES
          EVENT_SOURCES.forEach(source => {
            entry[source] = bucket.sources && bucket.sources[source] ? bucket.sources[source] : 0;
          });
          entry.anomaly_markers = bucket.anomaly_markers || [];
          return entry;
        });
        setEventsData(processed);
      }
    } catch (err) {
      console.error("Failed to fetch events:", err);
    } finally {
      setLoading(false);
    }
  };

  const fetchMetricsData = async () => {
    setLoading(true);
    try {
      const enabledSources = Object.entries(selectedSources)
        .filter(([_, v]) => v)
        .map(([k]) => k)
        .filter(s => METRIC_SOURCES.includes(s))
        .join(",");
      
      const res = await fetch(
        `/api/analytics/metrics?hours=${hours}&bucket_minutes=${bucketMinutes}${enabledSources ? `&sources=${enabledSources}` : ""}`,
        { headers: getAuthHeaders() }
      );
      const data = await res.json();
      if (data.time_series) {
        const processed = data.time_series.map(bucket => {
          const entry = { time: bucket.bucket_start };
          // Zero-fill all METRIC_SOURCES x selectedMetric combinations
          METRIC_SOURCES.forEach(source => {
            const key = `${source}_${selectedMetric}`;
            entry[key] = bucket.metrics && bucket.metrics[source] && bucket.metrics[source][selectedMetric] !== undefined 
              ? bucket.metrics[source][selectedMetric] 
              : 0;
          });
          entry.anomaly_markers = bucket.anomaly_markers || [];
          return entry;
        });
        setMetricsData(processed);
      }
    } catch (err) {
      console.error("Failed to fetch metrics:", err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (activeTab === "events") {
      fetchEventsData();
    } else {
      fetchMetricsData();
    }
  }, [activeTab, hours, bucketMinutes, selectedSources]);

  useEffect(() => {
    const interval = setInterval(() => {
      if (activeTab === "events") {
        fetchEventsData();
      } else {
        fetchMetricsData();
      }
    }, 30000);
    return () => clearInterval(interval);
  }, [activeTab, hours, bucketMinutes, selectedSources]);

  const toggleSource = (source) => {
    setSelectedSources(prev => ({ ...prev, [source]: !prev[source] }));
  };

  const formatTime = (timeStr) => {
    const date = new Date(timeStr);
    return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  };

  const currentData = activeTab === "events" ? eventsData : metricsData;

  const getLines = () => {
    if (activeTab === "events") {
      return EVENT_SOURCES.filter(s => selectedSources[s]).map(source => ({
        key: source,
        color: SOURCE_COLORS[source]
      }));
    } else {
      return METRIC_SOURCES.filter(s => selectedSources[s]).map(source => ({
        key: `${source}_${selectedMetric}`,
        source,
        color: SOURCE_COLORS[source]
      }));
    }
  };

  const CustomTooltip = ({ active, payload, label }) => {
    if (active && payload && payload.length) {
      const markers = currentData.find(d => d.time === label)?.anomaly_markers || [];
      return (
        <div className="chartTooltip">
          <p className="chartTooltip__time">{label}</p>
          {payload.map((entry, index) => (
            <p key={index} style={{ color: entry.color }}>
              {entry.name}: {entry.value?.toFixed?.(2) ?? entry.value}
            </p>
          ))}
          {markers.length > 0 && (
            <div className="chartTooltip__markers">
              <p className="chartTooltip__markers-title">Anomalies:</p>
              {markers.map((m, i) => (
                <p key={i} className={`chartTooltip__marker chartTooltip__marker--${m.severity?.toLowerCase()}`}>
                  {m.type} - {m.severity}
                </p>
              ))}
            </div>
          )}
        </div>
      );
    }
    return null;
  };

  const getAnomalyMarkers = () => {
    const markers = [];
    currentData.forEach((dataPoint, index) => {
      if (dataPoint.anomaly_markers && dataPoint.anomaly_markers.length > 0) {
        const yMax = Math.max(...getLines().map(l => {
          const val = dataPoint[l.key];
          return typeof val === 'number' ? val : 0;
        }).filter(v => v > 0), 10);
        markers.push({
          x: dataPoint.time,
          y: yMax,
          markers: dataPoint.anomaly_markers,
          cx: index
        });
      }
    });
    return markers;
  };

  return (
    <div className="analyticsPage">
      <div className="analyticsPage__header">
        <h1>Analytics</h1>
        <p className="analyticsPage__subtitle">
          Real-time event and metrics timeline with anomaly detection overlay
        </p>
      </div>

      <div className="analyticsPage__controls">
        <div className="analyticsPage__tabs">
          <button
            className={`analyticsPage__tab ${activeTab === "events" ? "analyticsPage__tab--active" : ""}`}
            onClick={() => setActiveTab("events")}
          >
            <Activity size={16} />
            Events
          </button>
          <button
            className={`analyticsPage__tab ${activeTab === "metrics" ? "analyticsPage__tab--active" : ""}`}
            onClick={() => setActiveTab("metrics")}
          >
            <BarChart3 size={16} />
            Metrics
          </button>
        </div>

        <div className="analyticsPage__filters">
          <div className="analyticsPage__timeFilter">
            <span>Time Range:</span>
            {["1h", "6h", "24h", "7d"].map(h => (
              <button
                key={h}
                className={`analyticsPage__timeBtn ${hours === (h === "1h" ? 1 : h === "6h" ? 6 : h === "24h" ? 24 : 168) ? "analyticsPage__timeBtn--active" : ""}`}
                onClick={() => setHours(h === "1h" ? 1 : h === "6h" ? 6 : h === "24h" ? 24 : 168)}
              >
                {h}
              </button>
            ))}
          </div>

          {activeTab === "metrics" && (
            <select
              className="analyticsPage__metricSelect"
              value={selectedMetric}
              onChange={(e) => setSelectedMetric(e.target.value)}
            >
              <option value="jvm_memory_used_bytes">JVM Memory</option>
              <option value="kafka_throughput">Kafka Throughput</option>
              <option value="windows_os_snapshot">OS CPU</option>
              <option value="container/cpu/usage_time">Container CPU</option>
            </select>
          )}
        </div>
      </div>

      <div className="analyticsPage__sourceFilter">
        <span>Sources:</span>
        <div className="analyticsPage__sourceList">
          {(activeTab === "events" ? EVENT_SOURCES : METRIC_SOURCES).map(source => (
            <label key={source} className="analyticsPage__sourceLabel">
              <input
                type="checkbox"
                checked={selectedSources[source]}
                onChange={() => toggleSource(source)}
              />
              <span style={{ color: SOURCE_COLORS[source] }}>{source}</span>
            </label>
          ))}
        </div>
      </div>

      <div className="analyticsPage__chart">
        {loading ? (
          <div className="analyticsPage__loading">Loading data...</div>
        ) : currentData.length === 0 ? (
          <div className="analyticsPage__empty">No data available for the selected time range</div>
        ) : (
          <ResponsiveContainer width="100%" height={400}>
            <LineChart data={currentData} margin={{ top: 20, right: 30, left: 20, bottom: 20 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
              <XAxis
                dataKey="time"
                tickFormatter={formatTime}
                stroke="#9ca3af"
                tick={{ fontSize: 12 }}
              />
              <YAxis stroke="#9ca3af" tick={{ fontSize: 12 }} />
              <Tooltip content={<CustomTooltip />} />
              <Legend />
              {getLines().map(line => (
                <Line
                  key={line.key}
                  type="monotone"
                  dataKey={line.key}
                  stroke={line.color}
                  strokeWidth={2}
                  dot={false}
                  activeDot={{ r: 6 }}
                />
              ))}
              {getAnomalyMarkers().map((marker, idx) => (
                <ReferenceDot
                  key={idx}
                  x={marker.x}
                  y={Math.max(...getLines().map(l => currentData.find(d => d.time === marker.x)?.[l.key] || 0)) * 0.9}
                  r={8}
                  fill="#ef4444"
                  stroke="#fff"
                  strokeWidth={2}
                />
              ))}
            </LineChart>
          </ResponsiveContainer>
        )}
      </div>

      <div className="analyticsPage__legend">
        <div className="analyticsPage__legendItem">
          <span className="analyticsPage__legendDot" style={{ background: "#ef4444" }}></span>
          <span>Anomaly detected at time point</span>
        </div>
        <div className="analyticsPage__legendItem">
          <span className="analyticsPage__legendInfo">Data refreshes every 30 seconds</span>
        </div>
      </div>
    </div>
  );
}

export default Analytics;