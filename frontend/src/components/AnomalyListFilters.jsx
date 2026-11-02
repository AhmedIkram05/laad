import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "./ui/select";

/** Sort, entity, anomaly-type, severity and detector filters for the list. */
function AnomalyListFilters({
  sortBy,
  onSortChange,
  entitySelectValue,
  onEntityChange,
  atms,
  servers,
  anomalyTypeFilter,
  onAnomalyTypeChange,
  severityFilter,
  onSeverityChange,
  detectorTypeFilter,
  onDetectorTypeChange,
  hasActiveFilters,
  onClearFilters,
}) {
  return (
    <div className="flex flex-wrap gap-3 items-center">
      <div className="flex items-center gap-2">
        <span className="text-sm text-muted-foreground">Sort:</span>
        <Select value={sortBy} onValueChange={onSortChange}>
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
        <Select value={entitySelectValue} onValueChange={onEntityChange}>
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
        <Select value={anomalyTypeFilter} onValueChange={onAnomalyTypeChange}>
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
        <Select value={severityFilter} onValueChange={onSeverityChange}>
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
        <Select value={detectorTypeFilter} onValueChange={onDetectorTypeChange}>
          <SelectTrigger className="w-[160px]">
            <SelectValue placeholder="All Detectors" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All Detectors</SelectItem>
            <SelectItem value="ML_ENSEMBLE">ML Ensemble</SelectItem>
            <SelectItem value="HEURISTIC">Heuristic</SelectItem>
            <SelectItem value="ZSCORE">ZScore</SelectItem>
          </SelectContent>
        </Select>
      </div>

      {hasActiveFilters && (
        <button
          onClick={onClearFilters}
          className="text-sm text-muted-foreground hover:text-foreground underline"
        >
          Clear all
        </button>
      )}
    </div>
  );
}

export default AnomalyListFilters;
