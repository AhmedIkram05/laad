import { AlertCircle } from "lucide-react";
import AnomalyCard from "./AnomalyCard";
import { Skeleton } from "./ui/skeleton";

/** Renders the loading, error, empty, or card-list state of an anomaly page. */
function AnomalyListResults({
  loading,
  fetchError,
  pageAnomalies,
  formatTime,
  onStar,
  onCompleted,
}) {
  return (
    <div className="space-y-3">
      {loading ? (
        <div className="space-y-3">
          {Array.from({ length: 5 }).map((_, i) => (
            <Skeleton key={i} className="h-24 rounded-lg" />
          ))}
        </div>
      ) : fetchError ? (
        <div className="text-center py-12">
          <AlertCircle className="w-12 h-12 mx-auto text-destructive mb-4" />
          <p className="font-medium">Failed to load anomalies</p>
          <p className="text-muted-foreground text-sm mt-1">
            Something went wrong fetching the list. Please try again.
          </p>
        </div>
      ) : pageAnomalies.length === 0 ? (
        <div className="text-center py-12">
          <AlertCircle className="w-12 h-12 mx-auto text-muted-foreground mb-4" />
          <p className="text-muted-foreground">No anomalies found.</p>
        </div>
      ) : (
        pageAnomalies.map((a) => (
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
            toggle_star={onStar}
            onCompleted={onCompleted}
          />
        ))
      )}
    </div>
  );
}

export default AnomalyListResults;
