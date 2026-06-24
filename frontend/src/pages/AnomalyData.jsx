import { useParams } from "react-router-dom";
import { useEffect, useState } from "react";
import { Star, CheckCircle, Circle } from "lucide-react";
import { toast } from "sonner";
import { fetchAnomalies, fetchDetailedAnalysis, toggleComplete, toggleStar } from "../api/api";
import BackButton from "../components/BackButton";
import { Skeleton } from "../components/ui/skeleton";
import { Card, CardContent, CardHeader, CardTitle } from "../components/ui/card";
import { Badge } from "../components/ui/badge";
import { Button } from "../components/ui/button";
import { formatUKDateTime } from "../lib/utils";

const severityColors = {
  CRITICAL: "bg-destructive text-destructive-foreground",
  MAJOR: "bg-amber-500 text-white",
  HIGH: "bg-blue-500 text-white",
  LOW: "bg-muted text-muted-foreground",
};

function AnomalyData() {
  const { anomaly_type } = useParams();
  const [data, setData] = useState(null);
  const [isCompleted, setIsCompleted] = useState(true);
  const [isStarred, setIsStarred] = useState(false);
  const [dbAnomaly, setDbAnomaly] = useState(null);
  const [loaded, setLoaded] = useState(false);

  const handleComplete = async () => {
    if (!dbAnomaly) return;
    try {
      await toggleComplete(dbAnomaly.id);
      setIsCompleted(prev => !prev);
      toast.success(isCompleted ? "Marked as active" : "Marked as completed");
    } catch (err) {
      console.error("Failed to resolve anomaly", err);
      toast.error("Failed to update status");
    }
  };

  const handleStar = async () => {
    if (!dbAnomaly) return;
    try {
      await toggleStar(dbAnomaly.id);
      setIsStarred(prev => !prev);
    } catch (err) {
      console.error("Failed to toggle star", err);
    }
  };

  useEffect(() => {
    const load = async () => {
      try {
        const [analysisRes, anomaliesRes] = await Promise.all([
          fetchDetailedAnalysis(anomaly_type),
          fetchAnomalies(),
        ]);

        const analysis = analysisRes.data.find(
          (item) => item.Anomaly === anomaly_type
        ) || analysisRes.data[0];

        const matchedAnomaly = anomaliesRes.data.find(
          (a) => a.anomaly_type === anomaly_type
        );

        if (analysis) setData(analysis);
        if (matchedAnomaly) {
          setIsStarred(matchedAnomaly.is_starred === 1);
          setIsCompleted(matchedAnomaly.is_active === 0);
          setDbAnomaly(matchedAnomaly);
        }
      } catch (err) {
        console.error("Failed to fetch data", err);
      } finally {
        setLoaded(true);
      }
    };

    load();
  }, [anomaly_type]);

  if (!data && !loaded) return (
    <div className="space-y-4 p-4">
      <Skeleton className="h-8 w-1/2" />
      <Skeleton className="h-4 w-3/4" />
      <Skeleton className="h-32 w-full" />
    </div>
  );

  if (!data && loaded) return (
    <div className="space-y-4 p-4 text-center text-muted-foreground">
      <p>No analysis data available for this anomaly type.</p>
    </div>
  );

  const confidence = data.model_confidence_score ?? dbAnomaly?.model_confidence_score ?? null;
  const sources = data.sources_involved ?? dbAnomaly?.sources_involved ?? [];
  const recommendedAction = data.recommended_action || data.Recommended_Action;
  let detectionSource = data.detection_source;
  if (!detectionSource && dbAnomaly?.explanation) {
    try {
      const exp = JSON.parse(dbAnomaly.explanation);
      detectionSource = exp.source;
    } catch { /* explanation may be empty or non-JSON */ }
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-4">
        <BackButton />
        <div className="flex-1">
          <h1 className="text-2xl font-bold">{data.Title || "Title Unknown"}</h1>
          <p className="text-muted-foreground">Review analysis, understand the ATM issue, and follow the recommended actions.</p>
        </div>
      </div>

      <div className="flex gap-3">
        <Button variant={isStarred ? "default" : "outline"} onClick={handleStar}>
          <Star className={`w-4 h-4 mr-2 ${isStarred ? "fill-current" : ""}`} />
          {isStarred ? "Starred" : "Star"}
        </Button>
        <Button variant={isCompleted ? "secondary" : "default"} onClick={handleComplete}>
          {isCompleted ? <CheckCircle className="w-4 h-4 mr-2" /> : <Circle className="w-4 h-4 mr-2" />}
          {isCompleted ? "Completed" : "Mark Complete"}
        </Button>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="space-y-6">
          <Card>
            <CardHeader>
              <CardTitle className="text-lg">Root Cause</CardTitle>
            </CardHeader>
            <CardContent>
              <p className="text-muted-foreground">{data.root_cause || "Root Cause Unknown."}</p>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="text-lg">Operation Impact</CardTitle>
            </CardHeader>
            <CardContent>
              <p className="text-muted-foreground">{data.operations || "Operation Impact Unknown."}</p>
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="flex flex-row items-center justify-between">
              <CardTitle className="text-lg">Recommended Action</CardTitle>
              {recommendedAction && <Badge>Actionable</Badge>}
            </CardHeader>
            <CardContent>
              <p className="text-muted-foreground">{recommendedAction || "Recommended Action Unknown."}</p>
            </CardContent>
          </Card>
        </div>

        <div className="space-y-6">
          <Card>
            <CardHeader>
              <CardTitle className="text-lg">Details</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="flex justify-between">
                <span className="text-muted-foreground">ATM / Server:</span>
                <span className="font-mono">{data.ATM_ID ?? dbAnomaly?.atm_id ?? "SERVER"}</span>
              </div>
              <div className="flex justify-between items-center">
                <span className="text-muted-foreground">Severity:</span>
                <Badge className={severityColors[data.Severity] || ""}>{data.Severity || "Unknown"}</Badge>
              </div>
              <div className="flex justify-between">
                <span className="text-muted-foreground">Time Received:</span>
                <span>{data.Event_Time ? formatUKDateTime(data.Event_Time) : "Time Unknown"}</span>
              </div>
              {dbAnomaly?.correlation_id && (
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Correlation ID:</span>
                  <span className="font-mono text-sm">{dbAnomaly.correlation_id}</span>
                </div>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="text-lg">Detection</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              {confidence !== null && (
                <div>
                  <div className="flex justify-between text-sm mb-1">
                    <span className="text-muted-foreground">Confidence</span>
                    <span className="font-mono">{Math.round(confidence * 100)}%</span>
                  </div>
                  <div className="h-2 bg-secondary rounded-full overflow-hidden">
                    <div 
                      className={`h-full ${confidence >= 0.8 ? "bg-emerald-500" : confidence >= 0.6 ? "bg-amber-500" : "bg-red-500"}`}
                      style={{ width: `${confidence * 100}%` }}
                    />
                  </div>
                </div>
              )}
              {detectionSource && (
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Detected By:</span>
                  <Badge variant="outline">{detectionSource}</Badge>
                </div>
              )}
              {sources.length > 0 && (
                <div>
                  <span className="text-sm text-muted-foreground block mb-2">Sources:</span>
                  <div className="flex flex-wrap gap-2">
                    {sources.map((s) => (
                      <Badge key={s} variant="secondary">{s}</Badge>
                    ))}
                  </div>
                </div>
              )}
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}

export default AnomalyData;