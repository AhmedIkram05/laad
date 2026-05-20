import { useState, useEffect } from "react";
import { AlertCircle } from "lucide-react";
import { toast } from "sonner";
import SearchBar from "./SearchBar";
import AnomalyCard from "./AnomalyCard";
import { fetchAnomalies, toggleStar } from "../api/api";
import { Skeleton } from "./ui/skeleton";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "./ui/select";

const ITEMS_PER_PAGE = 20;

function AnomalyListPage({ title, subtitle, isActive = 1, isStarred = null }) {
  const [search, setSearch] = useState("");
  const [anomalies, setAnomalies] = useState([]);
  const [totalCount, setTotalCount] = useState(0);
  const [loading, setLoading] = useState(true);
  const [now, setNow] = useState(() => Date.now());
  const [sortBy, setSortBy] = useState("score");
  const [detectionSource, setDetectionSource] = useState("");
  const [atmIdFilter, setAtmIdFilter] = useState("");
  const [anomalyTypeFilter, setAnomalyTypeFilter] = useState("");
  const [severityFilter, setSeverityFilter] = useState("");
  const [currentPage, setCurrentPage] = useState(1);

  const hours = 24;

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      try {
        setLoading(true);
        const anomalyRes = await fetchAnomalies(isActive, hours, sortBy, undefined, isStarred);
        if (cancelled) return;
        const anomaliesData = anomalyRes?.data || [];
        setTotalCount(anomaliesData.length);
        const startIndex = (currentPage - 1) * ITEMS_PER_PAGE;
        setAnomalies(anomaliesData.slice(startIndex, startIndex + ITEMS_PER_PAGE));
      } catch (err) {
        console.error("Failed to fetch anomalies.", err);
      } finally {
        if (!cancelled) setLoading(false);
      }
    };
    load();
    return () => { cancelled = true; };
  }, [isActive, isStarred, hours, sortBy, currentPage]);

  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), 30_000);
    return () => clearInterval(timer);
  }, []);

  const handleStar = async (id) => {
    try {
      await toggleStar(id);
      setAnomalies(prev => prev.map(a => a.id === id ? { ...a, is_starred: !a.is_starred } : a));
    } catch (err) {
      toast.error("Failed to update star status");
    }
  };

  const handleCompleted = (id) => {
    setAnomalies(prev => prev.map(a => a.id === id ? { ...a, is_active: a.is_active === 0 ? 1 : 0 } : a));
  };

  const formatTime = (ts) => {
    try {
      const diff = Math.floor((now - new Date(ts)) / 60000);
      if (diff < 1) return "Just now";
      if (diff < 60) return `${diff}m ago`;
      return `${Math.floor(diff / 60)}h ago`;
    } catch { return "Unknown"; }
  };

  const searched = anomalies.filter(a => {
    if (!search) return true;
    const q = search.toLowerCase();
    return [a.title, a.anomaly_type, a.atm_id, a.severity].filter(Boolean).join(" ").toLowerCase().includes(q);
  });

  const totalPages = Math.ceil(totalCount / ITEMS_PER_PAGE);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">{title}</h1>
          <p className="text-muted-foreground mt-1">{subtitle}</p>
        </div>
        <div className="text-right">
          <p className="text-3xl font-bold font-mono">{totalCount}</p>
          <p className="text-sm text-muted-foreground">total anomalies</p>
        </div>
      </div>

      <SearchBar search={search} setSearch={setSearch} />

      <div className="space-y-3">
        {loading ? (
          <div className="space-y-3">
            {Array.from({ length: 5 }).map((_, i) => <Skeleton key={i} className="h-24 rounded-lg" />)}
          </div>
        ) : searched.length === 0 ? (
          <div className="text-center py-12">
            <AlertCircle className="w-12 h-12 mx-auto text-muted-foreground mb-4" />
            <p className="text-muted-foreground">No anomalies found.</p>
          </div>
        ) : (
          searched.map(a => (
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
          <button onClick={() => setCurrentPage(p => Math.max(1, p - 1))} disabled={currentPage === 1} className="px-3 py-1.5 border rounded disabled:opacity-50">Prev</button>
          <span className="px-3 py-1.5">Page {currentPage} of {totalPages}</span>
          <button onClick={() => setCurrentPage(p => Math.min(totalPages, p + 1))} disabled={currentPage === totalPages} className="px-3 py-1.5 border rounded disabled:opacity-50">Next</button>
        </div>
      )}
    </div>
  );
}

export default AnomalyListPage;