import { useState, useEffect, useMemo } from "react";
import { toast } from "sonner";
import {
  fetchAnomalies,
  toggleStar,
  toggleComplete,
  fetchEntities,
} from "../api/api";
import { useGlobalSearch } from "../components/SearchContext";

const ITEMS_PER_PAGE = 20;
// 60s: fresh enough that an ops list never sits stale on an open tab,
// slow enough not to hammer the API from every open tab.
const REFRESH_INTERVAL_MS = 60_000;

/**
 * Data layer for the anomaly list pages: fetching, polling, filtering,
 * pagination, and star/complete mutations. Presentation lives in the
 * AnomalyList* components so the page stays a thin container.
 */
export function useAnomalyList({ isActive = 1, isStarred = null }) {
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
  const [fetchError, setFetchError] = useState(false);

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
    let inFlight = false;
    const controller = new AbortController();
    const load = async (isIntervalRefresh = false) => {
      // Mirrors Analytics: skip a tick whose predecessor is still running.
      if (inFlight) return;
      inFlight = true;
      try {
        if (!isIntervalRefresh) {
          setLoading(true);
        }
        const anomalyRes = await fetchAnomalies(
          isActive,
          undefined,
          sortBy,
          detectorTypeFilter !== "all" ? detectorTypeFilter : undefined,
          isStarred,
          atmIdFilter !== "all" ? atmIdFilter : undefined,
          anomalyTypeFilter !== "all" ? anomalyTypeFilter : undefined,
          severityFilter !== "all" ? severityFilter : undefined,
          entityTypeFilter !== "all" ? entityTypeFilter : undefined,
          controller.signal
        );
        if (cancelled) return;
        setAllAnomalies(anomalyRes?.data || []);
        setFetchError(false);
      } catch (err) {
        if (cancelled) return;
        // Fetch failures must be distinguishable from an empty result.
        setFetchError(true);
        console.error("Failed to fetch anomalies.", err);
      } finally {
        inFlight = false;
        if (!cancelled) setLoading(false);
      }
    };
    load();
    const timer = setInterval(() => load(true), REFRESH_INTERVAL_MS);
    return () => {
      cancelled = true;
      clearInterval(timer);
      controller.abort();
    };
  }, [
    isActive,
    isStarred,
    sortBy,
    atmIdFilter,
    anomalyTypeFilter,
    severityFilter,
    entityTypeFilter,
    detectorTypeFilter,
  ]);

  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), 30_000);
    return () => clearInterval(timer);
  }, []);

  const handleStar = async (id) => {
    try {
      await toggleStar(id);
      setAllAnomalies((prev) =>
        prev.map((a) => (a.id === id ? { ...a, is_starred: !a.is_starred } : a))
      );
    } catch {
      toast.error("Failed to update star status");
    }
  };

  const handleCompleted = async (id) => {
    setAllAnomalies((prev) =>
      prev.map((a) =>
        a.id === id ? { ...a, is_active: a.is_active === 0 ? 1 : 0 } : a
      )
    );
    try {
      await toggleComplete(id);
    } catch {
      setAllAnomalies((prev) =>
        prev.map((a) =>
          a.id === id ? { ...a, is_active: a.is_active === 0 ? 1 : 0 } : a
        )
      );
      toast.error("Failed to update completion status");
    }
  };

  const formatTime = (ts) => {
    try {
      const diff = Math.floor((now - new Date(ts)) / 60000);
      if (Number.isNaN(diff)) return "Unknown";
      if (diff < 1) return "Just now";
      if (diff < 60) return `${diff}m ago`;
      return `${Math.floor(diff / 60)}h ago`;
    } catch {
      return "Unknown";
    }
  };

  const filtered = useMemo(() => {
    if (!query) return allAnomalies;
    const q = query.toLowerCase();
    return allAnomalies.filter((a) => {
      const displayEntityType = a.atm_id?.startsWith("ATM-SERVER-")
        ? "server"
        : "atm";
      const displayAtmId = a.atm_id ?? "";
      return [a.title, a.anomaly_type, displayAtmId, displayEntityType, a.severity]
        .filter(Boolean)
        .join(" ")
        .toLowerCase()
        .includes(q);
    });
  }, [allAnomalies, query]);

  const totalCount = filtered.length;
  const totalPages = Math.ceil(totalCount / ITEMS_PER_PAGE);
  // Clamp the active page to the result set: a filter change that shrinks the
  // list must not leave a stale page N>totalPages rendering an empty slice.
  const safePage = Math.min(currentPage, Math.max(totalPages, 1));
  const startIndex = (safePage - 1) * ITEMS_PER_PAGE;
  const pageAnomalies = filtered.slice(startIndex, startIndex + ITEMS_PER_PAGE);

  const atms = entities.filter((e) => e.atm_id.startsWith("ATM-GB-"));
  const servers = entities.filter((e) => e.atm_id.startsWith("ATM-SERVER-"));

  const clearFilters = () => {
    setAtmIdFilter("all");
    setAnomalyTypeFilter("all");
    setSeverityFilter("all");
    setEntityTypeFilter("all");
    setDetectorTypeFilter("all");
    setSortBy("score");
    setCurrentPage(1);
  };

  const hasActiveFilters =
    atmIdFilter !== "all" ||
    anomalyTypeFilter !== "all" ||
    severityFilter !== "all" ||
    entityTypeFilter !== "all" ||
    detectorTypeFilter !== "all" ||
    sortBy !== "score";

  const entitySelectValue =
    atmIdFilter === "all" && entityTypeFilter === "all"
      ? "all"
      : entityTypeFilter !== "all"
        ? entityTypeFilter
        : atmIdFilter;

  const handleEntityChange = (v) => {
    if (v === "all") {
      setEntityTypeFilter("all");
      setAtmIdFilter("all");
    } else if (v === "atm") {
      setEntityTypeFilter("atm");
      setAtmIdFilter("all");
    } else if (v === "server") {
      setEntityTypeFilter("server");
      setAtmIdFilter("all");
    } else {
      setEntityTypeFilter("all");
      setAtmIdFilter(v);
    }
  };

  return {
    // state
    loading,
    fetchError,
    sortBy,
    setSortBy,
    anomalyTypeFilter,
    setAnomalyTypeFilter,
    severityFilter,
    setSeverityFilter,
    detectorTypeFilter,
    setDetectorTypeFilter,
    atms,
    servers,
    entitySelectValue,
    handleEntityChange,
    currentPage,
    setCurrentPage,
    // derived
    totalCount,
    totalPages,
    safePage,
    pageAnomalies,
    hasActiveFilters,
    // handlers
    handleQueryChange,
    handleStar,
    handleCompleted,
    formatTime,
    clearFilters,
  };
}
