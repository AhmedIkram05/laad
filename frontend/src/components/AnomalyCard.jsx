import { useNavigate } from "react-router-dom";
import { AlertTriangle, CheckCircle, Circle, Star } from "lucide-react";
import { cn } from "../lib/utils";
import { Button } from "./ui/button";
import { Badge } from "./ui/badge";

const severityColors = {
  CRITICAL: "bg-destructive text-destructive-foreground",
  MAJOR: "bg-amber-500 text-white",
  HIGH: "bg-blue-500 text-white",
  LOW: "bg-muted text-muted-foreground",
};

export default function AnomalyCard({
  id,
  title,
  atm_id,
  severity,
  anomaly_type,
  update_time,
  is_starred,
  is_active,
  toggle_star,
  onCompleted,
}) {
  const navigate = useNavigate();

  return (
    <div className={cn(
      "group bg-card border border-border rounded-lg p-4",
      "hover:shadow-md hover:border-primary/20 transition-all duration-150"
    )}>
      <div className="flex items-start justify-between gap-4">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-2">
            <AlertTriangle className="w-4 h-4 text-destructive shrink-0" />
            <h3 className="font-medium text-foreground truncate">{title}</h3>
          </div>
          <div className="flex flex-wrap items-center gap-2 text-sm">
            <span className="font-mono text-muted-foreground">{atm_id}</span>
            <Badge variant="secondary" className={cn("text-xs", severityColors[severity])}>
              {severity}
            </Badge>
            <span className="text-muted-foreground">{update_time}</span>
          </div>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          <Button
            variant="outline"
            size="sm"
            onClick={() => navigate(`/data/${anomaly_type}`)}
          >
            View
          </Button>
          <button
            onClick={() => toggle_star(id)}
            className="p-1.5 rounded-md hover:bg-secondary transition-colors"
            aria-label={is_starred ? "Unstar anomaly" : "Star anomaly"}
          >
            <Star
              className={cn(
                "w-4 h-4 transition-colors",
                is_starred ? "fill-amber-400 text-amber-400" : "text-muted-foreground"
              )}
            />
          </button>
          <button
            onClick={() => onCompleted(id)}
            className="p-1.5 rounded-md hover:bg-secondary transition-colors"
            aria-label={is_active ? "Mark as completed" : "Mark as active"}
          >
            {is_active === 0 ? (
              <CheckCircle className="w-4 h-4 text-emerald-500" />
            ) : (
              <Circle className="w-4 h-4 text-muted-foreground" />
            )}
          </button>
        </div>
      </div>
    </div>
  );
}