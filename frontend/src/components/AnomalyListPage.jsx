import { useState, useEffect, useMemo } from "react";
import { AlertCircle } from "lucide-react";
import { toast } from "sonner";
import SearchBar from "./SearchBar";
import AnomalyCard from "./AnomalyCard";
import { fetchAnomalies, toggleStar, toggleComplete, fetchEntities } from "../api/api";
import { Skeleton } from "./ui/skeleton";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "./ui/select";
import { useGlobalSearch } from "./SearchContext";

const ITEMS_PER_PAGE = 20;

function AnomalyListPage({ title, subtitle, isActive = 1, isStarred = null }) {
  const { query, setQuery } = useGlobalSearch();
  const [allAnomalies, setAllAnomalies] = useState([]);
  const [loading, setLoading] = useState(true);
  const [now, setNow] = useState(() => Date.now());
  const [sortBy, setSortBy] = useState("score");
  const [atmIdFilter, setAtmIdFilter] = useState("all");
  const [anomalyTypeFilter, setAnomalyTypeFilter] = useState("all");
  const [severityFilter, setSeverityFilter] = useState("all");
  const [entityTypeFilter, setEntityTypeFilter] = useState("all");
  const [detectorTypeFilter, setDetectorTypeFilter] = useState("all");
  const [entities, setEntities] = useState([]);
  const [currentPage, setCurrentPage] = useState(1);

  const handleQueryChange = (newQuery) => {
    setQuery(newQuery);
    setCurrentPage(1);
  };

  useEffect(() => {
    fetchEntities()
      .then((data) => setEntities(data.entities || []))
      .catch(() => toast.error("Failed to load entities"));
  }, []);

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      try {
        setLoading(true);
        const anomalyRes = await fetchAnomalies(
          isActive,
          undefined,
          sortBy,
          detectorTypeFilter !== "all" ? detectorTypeFilter : undefined,
          isStarred,
          atmIdFilter !== "all" ? atmIdFilter : undefined,
          anomalyTypeFilter !== "all" ? anomalyTypeFilter : undefined,
          severityFilter !== "all" ? severityFilter : undefined,
          entityTypeFilter !== "all" ? entityTypeFilter : undefined
        );
        if (cancelled) return;
        setAllAnomalies(anomalyRes?.data || []);
      } catch (err) {
        console.error("Failed to fetch anomalies.", err);
      } finally {
        if (!cancelled) setLoading(false);
      }
    };
    load();
    return () => { cancelled = true; };
  }, [isActive, isStarred, sortBy, atmIdFilter, anomalyTypeFilter, severityFilter, entityTypeFilter, detectorTypeFilter]);

  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), 30_000);
    return () => clearInterval(timer);
  }, []);

  const handleStar = async (id) => {
    try {
      await toggleStar(id);
      setAllAnomalies(prev => prev.map(a => a.id === id ? { ...a, is_starred: !a.is_starred } : a));
    } catch {
      toast.error("Failed to update star status");
    }
  };

  const handleCompleted = async (id) => {
    setAllAnomalies(prev => prev.map(a => a.id === id ? { ...a, is_active: a.is_active === 0 ? 1 : 0 } : a));
    try {
      await toggleComplete(id);
    } catch {
      setAllAnomalies(prev => prev.map(a => a.id === id ? { ...a, is_active: a.is_active === 0 ? 1 : 0 } : a));
      toast.error("Failed to update completion status");
    }
  };

  const formatTime = (ts) => {
    try {
      const diff = Math.floor((now - new Date(ts)) / 60000);
      if (diff < 1) return "Just now";
      if (diff < 60) return `${diff}m ago`;
      return `${Math.floor(diff / 60)}h ago`;
    } catch { return "Unknown"; }
  };

  const filtered = useMemo(() => {
    if (!query) return allAnomalies;
    const q = query.toLowerCase();
    return allAnomalies.filter(a => {
      const displayEntityType = a.atm_id?.startsWith("ATM-SERVER-") ? "server" : "atm";
      const displayAtmId = a.atm_id ?? "";
      return [a.title, a.anomaly_type, displayAtmId, displayEntityType, a.severity]
        .filter(Boolean).join(" ").toLowerCase().includes(q);
    });
  }, [allAnomalies, query]);

  const totalCount = filtered.length;
  const totalPages = Math.ceil(totalCount / ITEMS_PER_PAGE);
  const startIndex = (currentPage - 1) * ITEMS_PER_PAGE;
  const pageAnomalies = filtered.slice(startIndex, startIndex + ITEMS_PER_PAGE);

  const atms = entities.filter(e => e.atm_id.startsWith("ATM-GB-"));
  const servers = entities.filter(e => e.atm_id.startsWith("ATM-SERVER-"));

  const clearFilters = () => {
    setAtmIdFilter("all");
    setAnomalyTypeFilter("all");
    setSeverityFilter("all");
    setEntityTypeFilter("all");
    setDetectorTypeFilter("all");
    setSortBy("score");
    setCurrentPage(1);
  };

  const hasActiveFilters = atmIdFilter !== "all" || anomalyTypeFilter !== "all" || severityFilter !== "all" || entityTypeFilter !== "all" || detectorTypeFilter !== "all" || sortBy !== "score";

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">{title}</h1>
          <p className="text-muted-foreground mt-1">{subtitle}</p>
        </div>
        <div className="text-right">
          <p className="text-3xl font-bold font-mono">{totalCount}</p>
          <p className="text-sm text-muted-foreground">matching anomalies</p>
        </div>
      </div>

      <SearchBar onQueryChange={handleQueryChange} />

      <div className="flex flex-wrap gap-3 items-center">
        <div className="flex items-center gap-2">
          <span className="text-sm text-muted-foreground">Sort:</span>
          <Select value={sortBy} onValueChange={setSortBy}>
            <SelectTrigger className="w-[160px]">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="score">Criticality Score</SelectItem>
              <SelectItem value="detected_at">Most Recent</SelectItem>
              <SelectItem value="severity">Severity</SelectItem>
            </SelectContent>
          </Select>
        </div>

        <div className="flex items-center gap-2">
          <span className="text-sm text-muted-foreground">Entity:</span>
          <Select value={atmIdFilter === "all" && entityTypeFilter === "all" ? "all" : entityTypeFilter !== "all" ? entityTypeFilter : atmIdFilter} onValueChange={(v) => {
            if (v === "all") { setEntityTypeFilter("all"); setAtmIdFilter("all"); }
            else if (v === "atm") { setEntityTypeFilter("atm"); setAtmIdFilter("all"); }
            else if (v === "server") { setEntityTypeFilter("server"); setAtmIdFilter("all"); }
            else { setEntityTypeFilter("all"); setAtmIdFilter(v); }
          }}>
            <SelectTrigger className="w-[180px]">
              <SelectValue placeholder="All Entities" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All Entities</SelectItem>
              <SelectItem value="atm">ATMs Only</SelectItem>
              <SelectItem value="server">Servers Only</SelectItem>
              {atms.length > 0 && (
                <>
                  <SelectItem value="__sep_atms" disabled>── ATMs ──</SelectItem>
                  {atms.map((e) => (
                    <SelectItem key={e.atm_id} value={e.atm_id}>{e.atm_id}</SelectItem>
                  ))}
                </>
              )}
              {servers.length > 0 && (
                <>
                  <SelectItem value="__sep_servers" disabled>── Servers ──</SelectItem>
                  {servers.map((e) => (
                    <SelectItem key={e.atm_id} value={e.atm_id}>{e.atm_id}</SelectItem>
                  ))}
                </>
              )}
            </SelectContent>
          </Select>
        </div>

        <div className="flex items-center gap-2">
          <span className="text-sm text-muted-foreground">Anomaly:</span>
          <Select value={anomalyTypeFilter} onValueChange={setAnomalyTypeFilter}>
            <SelectTrigger className="w-[160px]">
              <SelectValue placeholder="All Types" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All Types</SelectItem>
              <SelectItem value="A1">A1 - Network Timeout</SelectItem>
              <SelectItem value="A2">A2 - Cash Cassette</SelectItem>
              <SelectItem value="A3">A3 - JVM Memory</SelectItem>
              <SelectItem value="A4">A4 - Container Restart</SelectItem>
              <SelectItem value="A5">A5 - Response Time</SelectItem>
              <SelectItem value="A6">A6 - OS Memory</SelectItem>
              <SelectItem value="A7">A7 - Out-of-Order</SelectItem>
              <SelectItem value="UNKNOWN">UNKNOWN</SelectItem>
            </SelectContent>
          </Select>
        </div>

        <div className="flex items-center gap-2">
          <span className="text-sm text-muted-foreground">Severity:</span>
          <Select value={severityFilter} onValueChange={setSeverityFilter}>
            <SelectTrigger className="w-[160px]">
              <SelectValue placeholder="All Severities" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All Severities</SelectItem>
              <SelectItem value="CRITICAL">CRITICAL</SelectItem>
              <SelectItem value="HIGH">HIGH</SelectItem>
              <SelectItem value="MAJOR">MAJOR</SelectItem>
            </SelectContent>
          </Select>
        </div>

        <div className="flex items-center gap-2">
          <span className="text-sm text-muted-foreground">Detector:</span>
          <Select value={detectorTypeFilter} onValueChange={setDetectorTypeFilter}>
            <SelectTrigger className="w-[160px]">
              <SelectValue placeholder="All Detectors" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All Detectors</SelectItem>
              <SelectItem value="CLASSIFIER">Classifier</SelectItem>
              <SelectItem value="SIGNAL_CORRELATOR">Signal Correlator</SelectItem>
              <SelectItem value="ZSCORE">ZScore</SelectItem>
            </SelectContent>
          </Select>
        </div>

        {hasActiveFilters && (
          <button
            onClick={clearFilters}
            className="text-sm text-muted-foreground hover:text-foreground underline"
          >
            Clear all
          </button>
        )}
      </div>

      <div className="space-y-3">
        {loading ? (
          <div className="space-y-3">
            {Array.from({ length: 5 }).map((_, i) => <Skeleton key={i} className="h-24 rounded-lg" />)}
          </div>
        ) : pageAnomalies.length === 0 ? (
          <div className="text-center py-12">
            <AlertCircle className="w-12 h-12 mx-auto text-muted-foreground mb-4" />
            <p className="text-muted-foreground">No anomalies found.</p>
          </div>
        ) : (
          pageAnomalies.map(a => (
            <AnomalyCard
              key={a.id}
              id={a.id}
              title={a.title || "Unknown"}
              atm_id={a.atm_id ?? "SERVER"}
              severity={a.severity || "Unknown"}
              anomaly_type={a.anomaly_type}
              update_time={formatTime(a.detected_at)}
              is_starred={a.is_starred}
              is_active={a.is_active}
              toggle_star={handleStar}
              onCompleted={handleCompleted}
            />
          ))
        )}
      </div>

      {totalPages > 1 && (
        <div className="flex justify-center gap-2">
          <button onClick={() => setCurrentPage(1)} disabled={currentPage === 1} className="px-3 py-1.5 border rounded disabled:opacity-50">First</button>
          <button onClick={() => setCurrentPage(p => Math.max(1, p - 1))} disabled={currentPage === 1} className="px-3 py-1.5 border rounded disabled:opacity-50">Prev</button>
          <span className="px-3 py-1.5">Page {currentPage} of {totalPages}</span>
          <button onClick={() => setCurrentPage(p => Math.min(totalPages, p + 1))} disabled={currentPage === totalPages} className="px-3 py-1.5 border rounded disabled:opacity-50">Next</button>
          <button onClick={() => setCurrentPage(totalPages)} disabled={currentPage === totalPages} className="px-3 py-1.5 border rounded disabled:opacity-50">Last</button>
        </div>
      )}
    </div>
  );
}

export default AnomalyListPage;
