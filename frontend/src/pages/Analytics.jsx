import { useState, useEffect, useRef } from "react";
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  BarElement,
  ArcElement,
  Title,
  Tooltip,
  Legend,
  Filler,
} from "chart.js";
import { Line, Bar, Doughnut } from "react-chartjs-2";
import {
  Activity,
  AlertTriangle,
  Server,
  TrendingUp,
  Clock,
  RefreshCw,
  Filter,
} from "lucide-react";
import { Card, CardHeader, CardTitle, CardContent } from "../components/ui/card";
import { Skeleton } from "../components/ui/skeleton";
import { Badge } from "../components/ui/badge";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "../components/ui/select";
import { Button } from "../components/ui/button";
import { getAuthHeaders } from "../api/api";
import { toast } from "sonner";

ChartJS.register(
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  BarElement,
  ArcElement,
  Title,
  Tooltip,
  Legend,
  Filler
);

const TIME_RANGES = [
  { label: "1 Hour", value: 1, bucket: 5 },
  { label: "6 Hours", value: 6, bucket: 15 },
  { label: "24 Hours", value: 24, bucket: 60 },
  { label: "7 Days", value: 168, bucket: 360 },
  { label: "All Time", value: 0, bucket: 1440 },
];

const EVENT_SOURCES = ["ATM_APP", "HARDWARE", "TERMINAL_HANDLER"];
const METRIC_SOURCES = ["KAFKA", "PROMETHEUS", "OS", "CLOUD"];

const SOURCE_COLORS = {
  ATM_APP: { bg: "rgba(59, 130, 246, 0.6)", border: "#3b82f6" },
  HARDWARE: { bg: "rgba(16, 185, 129, 0.6)", border: "#10b981" },
  TERMINAL_HANDLER: { bg: "rgba(245, 158, 11, 0.6)", border: "#f59e0b" },
  KAFKA: { bg: "rgba(139, 92, 246, 0.6)", border: "#8b5cf6" },
  PROMETHEUS: { bg: "rgba(236, 72, 153, 0.6)", border: "#ec4899" },
  OS: { bg: "rgba(20, 184, 166, 0.6)", border: "#14b8a6" },
  CLOUD: { bg: "rgba(99, 102, 241, 0.6)", border: "#6366f1" },
};

const SEVERITY_COLORS = {
  CRITICAL: "#ef4444",
  MAJOR: "#f59e0b",
  HIGH: "#f97316",
  LOW: "#22c55e",
};

function formatNumber(num) {
  if (num >= 1000000) return (num / 1000000).toFixed(1) + "M";
  if (num >= 1000) return (num / 1000).toFixed(1) + "K";
  return num?.toString() || "0";
}

function formatTimeLabel(dateStr) {
  const d = new Date(dateStr);
  return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

const SOURCE_DISPLAY_NAMES = {
  ATM_APP: "ATM Application",
  HARDWARE: "Hardware Sensor",
  TERMINAL_HANDLER: "Terminal Handler",
  KAFKA: "Kafka Metrics",
  PROMETHEUS: "Prometheus Metrics",
  OS: "Windows OS",
  CLOUD: "GCP Cloud",
};

const ACRONYMS = new Set(["ATM", "CPU", "JVM", "OS", "GCP", "IO", "RT", "MS", "API"]);

function normaliseMetricName(str) {
  return str
    .split(/[/_]/)
    .map((word) => {
      if (!word) return word;
      const upper = word.toUpperCase();
      if (ACRONYMS.has(upper)) return upper;
      return word.charAt(0).toUpperCase() + word.slice(1).toLowerCase();
    })
    .join(" ");
}

function normaliseSource(str) {
  return SOURCE_DISPLAY_NAMES[str] || str;
}

function StatCard({ icon, title, value, subtitle, loading, trend }) {
  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
        <CardTitle className="text-sm font-medium text-muted-foreground">
          {title}
        </CardTitle>
        {icon}
      </CardHeader>
      <CardContent>
        {loading ? (
          <Skeleton className="h-8 w-24" />
        ) : (
          <>
            <div className="text-2xl font-bold">{formatNumber(value)}</div>
            <div className="flex items-center gap-1 mt-1">
              {trend && (
                <TrendingUp
                  className={`h-3 w-3 ${trend > 0 ? "text-green-500" : "text-red-500"}`}
                />
              )}
              <p className="text-xs text-muted-foreground">
                {subtitle || "Last updated just now"}
              </p>
            </div>
          </>
        )}
      </CardContent>
    </Card>
  );
}

function ChartCard({ title, children, loading, actions }) {
  return (
    <Card className="col-span-1 lg:col-span-2">
      <CardHeader className="flex flex-row items-center justify-between">
        <CardTitle className="text-lg">{title}</CardTitle>
        <div className="flex items-center gap-2">
          {actions}
          {loading && <RefreshCw className="h-4 w-4 animate-spin text-muted-foreground" />}
        </div>
      </CardHeader>
      <CardContent>
        {loading ? (
          <Skeleton className="h-64 w-full" />
        ) : (
          children
        )}
      </CardContent>
    </Card>
  );
}

function Analytics() {
  const [timeRange, setTimeRange] = useState(TIME_RANGES[2]);
  const [selectedEventSources, setSelectedEventSources] = useState(EVENT_SOURCES);
  const [selectedMetricSources] = useState(METRIC_SOURCES);

  const [realtimeStats, setRealtimeStats] = useState({
    events_by_source: {},
    anomaly_types: {},
    unique_atms: 0,
  });
  const [eventsData, setEventsData] = useState([]);
  const [metricsData, setMetricsData] = useState([]);
  const [availableMetrics, setAvailableMetrics] = useState([]);
  const [selectedMetrics, setSelectedMetrics] = useState([]);
  const [refreshKey, setRefreshKey] = useState(0);

  const [loadingRealtime, setLoadingRealtime] = useState(true);
  const [loadingEvents, setLoadingEvents] = useState(true);
  const [loadingMetrics, setLoadingMetrics] = useState(true);

  const intervalRef = useRef(null);

  useEffect(() => {
    let ignore = false;

    const loadData = async (isIntervalRefresh) => {
      try {
        if (!isIntervalRefresh) {
          setLoadingEvents(true);
          setLoadingMetrics(true);
        }

        const [realtimeRes, eventsRes, metricsRes, metricsListRes] = await Promise.all([
          fetch(`/api/insights/stats/realtime?hours=${timeRange.value}`, { headers: getAuthHeaders() }),
          fetch(
            `/api/insights/events?hours=${timeRange.value}&bucket_minutes=${timeRange.bucket}&sources=${selectedEventSources.join(",")}`,
            { headers: getAuthHeaders() }
          ),
          fetch(
            `/api/insights/metrics?hours=${timeRange.value}&bucket_minutes=${timeRange.bucket}&sources=${selectedMetricSources.join(",")}`,
            { headers: getAuthHeaders() }
          ),
          fetch("/api/insights/metrics/list", { headers: getAuthHeaders() }),
        ]);

        if (ignore) return;

        if (realtimeRes.ok) {
          setRealtimeStats(await realtimeRes.json());
          setLoadingRealtime(false);
        }
        if (eventsRes.ok) {
          setEventsData((await eventsRes.json()).time_series || []);
        } else {
          toast.error("Failed to load events data");
          setEventsData([]);
        }
        if (metricsRes.ok) {
          setMetricsData((await metricsRes.json()).time_series || []);
        } else {
          toast.error("Failed to load metrics data");
          setMetricsData([]);
        }
        setLoadingEvents(false);
        setLoadingMetrics(false);

        if (metricsListRes.ok) {
          const data = await metricsListRes.json();
          setAvailableMetrics(data.metrics || []);
          if (data.metrics?.length > 0 && selectedMetrics.length === 0) {
            setSelectedMetrics(data.metrics.slice(0, 3));
          }
        }
      } catch (err) {
        if (ignore) return;
        console.error("Failed to fetch analytics data:", err);
        toast.error("Failed to load analytics data");
        setLoadingRealtime(false);
        setLoadingEvents(false);
        setLoadingMetrics(false);
      }
    };

    loadData(false);

    intervalRef.current = setInterval(() => loadData(true), 5000);

    return () => {
      ignore = true;
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  }, [timeRange, selectedEventSources, selectedMetricSources, selectedMetrics.length, refreshKey]);

  const totalEvents = Object.values(realtimeStats.events_by_source || {}).reduce(
    (a, b) => a + b,
    0
  );
  const totalAnomalies = Object.values(realtimeStats.anomaly_types || {}).reduce(
    (a, b) => a + b,
    0
  );

  const eventsChartData = {
    labels: eventsData.map((d) => formatTimeLabel(d.bucket_start)),
    datasets: selectedEventSources.map((source) => ({
      label: normaliseSource(source),
      data: eventsData.map((d) => d.sources[source] || 0),
      backgroundColor: SOURCE_COLORS[source]?.bg || "rgba(100,100,100,0.5)",
      borderColor: SOURCE_COLORS[source]?.border || "#666",
      borderWidth: 1,
    })),
  };

  const eventsChartOptions = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: { position: "top" },
      tooltip: {
        mode: "index",
        intersect: false,
      },
    },
    scales: {
      x: { stacked: true, grid: { display: false } },
      y: { stacked: true, beginAtZero: true },
    },
  };

  const allMetricNames = [...new Set(
    metricsData.flatMap((d) =>
      Object.values(d.metrics || {}).flatMap((m) => Object.keys(m))
    )
  )];

  const metricsChartData = {
    labels: metricsData.map((d) => formatTimeLabel(d.bucket_start)),
    datasets: selectedMetrics
      .filter((m) => allMetricNames.includes(m))
      .map((metric, idx) => {
        const colors = ["#3b82f6", "#10b981", "#f59e0b", "#ef4444", "#8b5cf6", "#ec4899"];
        return {
          label: normaliseMetricName(metric),
          data: metricsData.map((d) => {
            for (const source of Object.values(d.metrics || {})) {
              if (source[metric] !== undefined) return source[metric];
            }
            return null;
          }),
          borderColor: colors[idx % colors.length],
          backgroundColor: colors[idx % colors.length] + "20",
          fill: true,
          tension: 0.4,
          pointRadius: 2,
          pointHoverRadius: 5,
        };
      }),
  };

  const metricsChartOptions = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: { position: "top" },
      tooltip: { mode: "index", intersect: false },
    },
    scales: {
      x: { grid: { display: false } },
      y: { beginAtZero: true },
    },
  };

  const anomalyTypeData = realtimeStats.anomaly_types || {};
  const anomalyChartData = {
    labels: Object.keys(anomalyTypeData).map(normaliseMetricName),
    datasets: [
      {
        data: Object.values(anomalyTypeData),
        backgroundColor: Object.keys(anomalyTypeData).map(
          (_, i) =>
            ["#ef4444", "#f59e0b", "#f97316", "#22c55e", "#3b82f6", "#8b5cf6", "#ec4899"][i % 7]
        ),
        borderWidth: 0,
      },
    ],
  };

  const anomalyChartOptions = {
    responsive: true,
    maintainAspectRatio: false,
    cutout: "60%",
    plugins: {
      legend: { position: "right", labels: { boxWidth: 12, padding: 8 } },
    },
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Analytics</h1>
          <p className="text-muted-foreground mt-1">
            Real-time system monitoring and anomaly insights
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Select
            value={timeRange.value.toString()}
            onValueChange={(val) => {
              const tr = TIME_RANGES.find((t) => t.value === parseInt(val));
              if (tr) setTimeRange(tr);
            }}
          >
            <SelectTrigger className="w-[140px]">
              <Clock className="h-4 w-4 mr-2" />
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {TIME_RANGES.map((tr) => (
                <SelectItem key={tr.value} value={tr.value.toString()}>
                  {tr.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Button
            variant="outline"
            size="sm"
            onClick={() => setRefreshKey((k) => k + 1)}
          >
            <RefreshCw className="h-4 w-4 mr-1" />
            Refresh
          </Button>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard
          icon={<Activity className="h-4 w-4 text-muted-foreground" />}
          title="Total Events"
          value={totalEvents}
          subtitle={`${selectedEventSources.length} sources`}
          loading={loadingRealtime}
        />
        <StatCard
          icon={<AlertTriangle className="h-4 w-4 text-muted-foreground" />}
          title="Total Anomalies"
          value={totalAnomalies}
          subtitle={`${Object.keys(anomalyTypeData).length} types detected`}
          loading={loadingRealtime}
        />
        <StatCard
          icon={<Server className="h-4 w-4 text-muted-foreground" />}
          title="ATMs & Servers Being Monitored"
          value={realtimeStats.unique_atms}
          loading={loadingRealtime}
        />
        <StatCard
          icon={<Filter className="h-4 w-4 text-muted-foreground" />}
          title="Metric Types"
          value={availableMetrics.length}
          subtitle="Available for monitoring"
          loading={loadingRealtime}
        />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2">
          <ChartCard
            title="Event Volume by Source"
            loading={loadingEvents}
            actions={
              <div className="flex gap-1 flex-wrap">
                {EVENT_SOURCES.map((source) => (
                  <Badge
                    key={source}
                    variant={selectedEventSources.includes(source) ? "default" : "outline"}
                    className="cursor-pointer text-xs"
                    onClick={() => {
                      setSelectedEventSources((prev) =>
                        prev.includes(source)
                          ? prev.filter((s) => s !== source)
                          : [...prev, source]
                      );
                    }}
                  >
                    {normaliseSource(source)}
                  </Badge>
                ))}
              </div>
            }
          >
            <div className="h-64">
              <Bar data={eventsChartData} options={eventsChartOptions} />
            </div>
          </ChartCard>
        </div>

        <Card>
          <CardHeader>
            <CardTitle className="text-lg">Anomaly Distribution</CardTitle>
          </CardHeader>
          <CardContent>
            {loadingRealtime ? (
              <Skeleton className="h-48 w-full" />
            ) : Object.keys(anomalyTypeData).length === 0 ? (
              <p className="text-muted-foreground text-sm text-center py-8">
                No anomalies detected in this period
              </p>
            ) : (
              <div className="h-48">
                <Doughnut data={anomalyChartData} options={anomalyChartOptions} />
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      <ChartCard
        title="Metrics Timeline"
        loading={loadingMetrics}
        actions={
          <Select
            value={selectedMetrics[0] || ""}
            onValueChange={(val) => {
              if (val && !selectedMetrics.includes(val)) {
                setSelectedMetrics((prev) => [...prev.slice(-2), val]);
              }
            }}
          >
            <SelectTrigger className="w-[180px]">
              <SelectValue placeholder="Add metric..." />
            </SelectTrigger>
            <SelectContent>
              {availableMetrics
                .filter((m) => !selectedMetrics.includes(m))
                .map((m) => (
                  <SelectItem key={m} value={m}>
                    {normaliseMetricName(m)}
                  </SelectItem>
                ))}
            </SelectContent>
          </Select>
        }
      >
        <div className="flex gap-1 mb-2 flex-wrap">
          {selectedMetrics.map((m) => (
            <Badge
              key={m}
              variant="secondary"
              className="text-xs cursor-pointer"
              onClick={() =>
                setSelectedMetrics((prev) => prev.filter((x) => x !== m))
              }
            >
              {normaliseMetricName(m)} x
            </Badge>
          ))}
        </div>
        <div className="h-64">
          <Line data={metricsChartData} options={metricsChartOptions} />
        </div>
      </ChartCard>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <Card>
          <CardHeader>
            <CardTitle className="text-lg">Events by Source Breakdown</CardTitle>
          </CardHeader>
          <CardContent>
            {loadingRealtime ? (
              <Skeleton className="h-32 w-full" />
            ) : (
              <div className="space-y-3">
                {Object.entries(realtimeStats.events_by_source || {})
                  .sort((a, b) => b[1] - a[1])
                  .map(([source, count]) => (
                    <div key={source} className="flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        <div
                          className="w-3 h-3 rounded-full"
                          style={{
                            backgroundColor: SOURCE_COLORS[source]?.border || "#666",
                          }}
                        />
                        <span className="text-sm">{normaliseSource(source)}</span>
                      </div>
                      <span className="font-mono text-sm font-medium">
                        {formatNumber(count)}
                      </span>
                    </div>
                  ))}
                {Object.keys(realtimeStats.events_by_source || {}).length === 0 && (
                  <p className="text-muted-foreground text-sm text-center py-4">
                    No event data available
                  </p>
                )}
              </div>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-lg">Anomaly Type Frequency</CardTitle>
          </CardHeader>
          <CardContent>
            {loadingRealtime ? (
              <Skeleton className="h-32 w-full" />
            ) : (
              <div className="space-y-3">
                {Object.entries(anomalyTypeData)
                  .sort((a, b) => b[1] - a[1])
                  .map(([type, count]) => (
                    <div key={type} className="flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        <Badge
                          variant="outline"
                          className="text-xs"
                        >
                          {normaliseMetricName(type)}
                        </Badge>
                      </div>
                      <span className="font-mono text-sm font-medium">
                        {formatNumber(count)}
                      </span>
                    </div>
                  ))}
                {Object.keys(anomalyTypeData).length === 0 && (
                  <p className="text-muted-foreground text-sm text-center py-4">
                    No anomaly data available
                  </p>
                )}
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

export default Analytics;
