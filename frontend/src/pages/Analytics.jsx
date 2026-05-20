import { useState, useEffect, useCallback } from "react";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
  ReferenceLine
} from "recharts";
import { Activity, BarChart3, AlertCircle, RefreshCw } from "lucide-react";
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

const DEFAULT_EVENT_SOURCES = {
  ATM_APP: true,
  HARDWARE: true,
  TERMINAL_HANDLER: true
};

const DEFAULT_METRIC_SOURCES = {
  KAFKA: true,
  PROMETHEUS: true,
  OS: true,
  CLOUD: true
};

function Analytics() {
  const [activeTab, setActiveTab] = useState("events");
  const [hours, setHours] = useState(24);
  const [bucketMinutes, setBucketMinutes] = useState(60);
  const [eventsData, setEventsData] = useState([]);
  const [metricsData, setMetricsData] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [retryCount, setRetryCount] = useState(0);
  const [eventSources, setEventSources] = useState(DEFAULT_EVENT_SOURCES);
  const [metricSources, setMetricSources] = useState(DEFAULT_METRIC_SOURCES);
  const [selectedMetric, setSelectedMetric] = useState("jvm_memory_used_bytes");
  const [availableMetrics, setAvailableMetrics] = useState([
    { value: "jvm_memory_used_bytes", label: "JVM Memory" },
    { value: "kafka_throughput", label: "Kafka Throughput" },
    { value: "cpu_usage_percent", label: "OS CPU" },
    { value: "container_cpu_usage", label: "Container CPU" }
  ]);

  const fetchAvailableMetrics = useCallback(async () => {
    try {
      const res = await fetch("/api/analytics/metrics/list", { headers: getAuthHeaders() });
      if (res.ok) {
        const data = await res.json();
        if (data.metrics && data.metrics.length > 0) {
          setAvailableMetrics(data.metrics.map(m => ({
            value: m,
            label: m.replace(/_/g, " ").replace(/\b\w/g, c => c.toUpperCase())
          })));
        }
      }
    } catch (err) {
      console.warn("Failed to fetch available metrics, using defaults:", err);
    }
  }, []);

  const fetchEventsData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const enabledSources = Object.entries(eventSources)
        .filter(([_, v]) => v)
        .map(([k]) => k)
        .join(",");
      
      const res = await fetch(
        `/api/analytics/events?hours=${hours}&bucket_minutes=${bucketMinutes}${enabledSources ? `&sources=${enabledSources}` : ""}`,
        { headers: getAuthHeaders() }
      );
      
      if (!res.ok) {
        throw new Error(`HTTP ${res.status}: ${res.statusText}`);
      }
      
      const data = await res.json();
      if (data.error) {
        throw new Error(data.error);
      }
      
      if (data.time_series) {
        const processed = data.time_series.map(bucket => {
          const entry = { time: bucket.bucket_start };
          EVENT_SOURCES.forEach(source => {
            entry[source] = bucket.sources && bucket.sources[source] ? bucket.sources[source] : 0;
          });
          entry.anomaly_markers = bucket.anomaly_markers || [];
          return entry;
        });
        setEventsData(processed);
        setRetryCount(0);
      }
    } catch (err) {
      console.error("Failed to fetch events:", err);
      setError(err.message);
      if (retryCount < 3) {
        setTimeout(() => {
          setRetryCount(prev => prev + 1);
          fetchEventsData();
        }, 2000 * (retryCount + 1));
      }
    } finally {
      setLoading(false);
    }
  }, [hours, bucketMinutes, eventSources, retryCount]);

  const fetchMetricsData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const enabledSources = Object.entries(metricSources)
        .filter(([_, v]) => v)
        .map(([k]) => k)
        .join(",");
      
      const res = await fetch(
        `/api/analytics/metrics?hours=${hours}&bucket_minutes=${bucketMinutes}${enabledSources ? `&sources=${enabledSources}` : ""}`,
        { headers: getAuthHeaders() }
      );
      
      if (!res.ok) {
        throw new Error(`HTTP ${res.status}: ${res.statusText}`);
      }
      
      const data = await res.json();
      if (data.error) {
        throw new Error(data.error);
      }
      
      if (data.time_series) {
        const processed = data.time_series.map(bucket => {
          const entry = { time: bucket.bucket_start };
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
        setRetryCount(0);
      }
    } catch (err) {
      console.error("Failed to fetch metrics:", err);
      setError(err.message);
      if (retryCount < 3) {
        setTimeout(() => {
          setRetryCount(prev => prev + 1);
          fetchMetricsData();
        }, 2000 * (retryCount + 1));
      }
    } finally {
      setLoading(false);
    }
  }, [hours, bucketMinutes, metricSources, selectedMetric, retryCount]);

  useEffect(() => {
    fetchAvailableMetrics();
  }, [fetchAvailableMetrics]);

  useEffect(() => {
    if (activeTab === "events") {
      fetchEventsData();
    } else {
      fetchMetricsData();
    }
  }, [activeTab, hours, bucketMinutes]);

  useEffect(() => {
    if (activeTab === "events") {
      fetchEventsData();
    } else {
      fetchMetricsData();
    }
  }, [activeTab === "events" ? eventSources : metricSources, selectedMetric]);

  useEffect(() => {
    const interval = setInterval(() => {
      if (activeTab === "events") {
        fetchEventsData();
      } else {
        fetchMetricsData();
      }
    }, 30000);
    return () => clearInterval(interval);
  }, [activeTab, fetchEventsData, fetchMetricsData]);

  const toggleEventSource = (source) => {
    setEventSources(prev => ({ ...prev, [source]: !prev[source] }));
  };

  const toggleMetricSource = (source) => {
    setMetricSources(prev => ({ ...prev, [source]: !prev[source] }));
  };

  const formatTime = (timeStr) => {
    const date = new Date(timeStr);
    return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  };

  const currentData = activeTab === "events" ? eventsData : metricsData;

  const getLines = () => {
    if (activeTab === "events") {
      return EVENT_SOURCES.filter(s => eventSources[s]).map(source => ({
        key: source,
        color: SOURCE_COLORS[source]
      }));
    } else {
      return METRIC_SOURCES.filter(s => metricSources[s]).map(source => ({
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
          <p className="chartTooltip__time">{formatTime(label)}</p>
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
    currentData.forEach((dataPoint) => {
      if (dataPoint.anomaly_markers && dataPoint.anomaly_markers.length > 0) {
        markers.push({
          x: dataPoint.time,
          markers: dataPoint.anomaly_markers
        });
      }
    });
    return markers;
  };

  const renderChart = () => {
    if (loading) {
      return <div className="analyticsPage__loading"><RefreshCw className="analyticsPage__loadingSpinner" size={24} />Loading data...</div>;
    }

    if (error) {
      return (
        <div className="analyticsPage__error">
          <AlertCircle size={24} />
          <p>{error}</p>
          <button className="analyticsPage__retryBtn" onClick={() => {
            setRetryCount(0);
            if (activeTab === "events") fetchEventsData();
            else fetchMetricsData();
          }}>
            Retry
          </button>
        </div>
      );
    }

    if (currentData.length === 0) {
      return (
        <div className="analyticsPage__empty">
          <Activity size={48} className="analyticsPage__emptyIcon" />
          <p>No data available for the selected time range</p>
          <p className="analyticsPage__emptyHint">Try adjusting the time range or check if the data generator is running</p>
        </div>
      );
    }

    const anomalyMarkers = getAnomalyMarkers();

    return (
      <ResponsiveContainer width="100%" height={400}>
        <LineChart 
          data={currentData} 
          margin={{ top: 20, right: 30, left: 20, bottom: 20 }}
        >
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
          {anomalyMarkers.map((marker, idx) => (
            <ReferenceLine
              key={idx}
              x={marker.x}
              stroke="#ef4444"
              strokeDasharray="3 3"
              strokeWidth={1}
              opacity={0.6}
            />
          ))}
        </LineChart>
      </ResponsiveContainer>
    );
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
              {availableMetrics.map(metric => (
                <option key={metric.value} value={metric.value}>
                  {metric.label}
                </option>
              ))}
            </select>
          )}
        </div>
      </div>

      <div className="analyticsPage__sourceFilter">
        <span>Sources:</span>
        <div className="analyticsPage__sourceList">
          {(activeTab === "events" 
            ? EVENT_SOURCES.map(s => ({ source: s, checked: eventSources[s], toggle: toggleEventSource }))
            : METRIC_SOURCES.map(s => ({ source: s, checked: metricSources[s], toggle: toggleMetricSource }))
          ).map(({ source, checked, toggle }) => (
            <label key={source} className="analyticsPage__sourceLabel">
              <input
                type="checkbox"
                checked={checked}
                onChange={() => toggle(source)}
              />
              <span style={{ color: SOURCE_COLORS[source] }}>{source}</span>
            </label>
          ))}
        </div>
      </div>

      <div className="analyticsPage__chart">
        {renderChart()}
      </div>

      <div className="analyticsPage__legend">
        <div className="analyticsPage__legendItem">
          <span className="analyticsPage__legendLine" style={{ background: "#ef4444" }}></span>
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
