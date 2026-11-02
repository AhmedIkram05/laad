import SearchBar from "./SearchBar";
import AnomalyListFilters from "./AnomalyListFilters";
import AnomalyListResults from "./AnomalyListResults";
import AnomalyListPagination from "./AnomalyListPagination";
import { useAnomalyList } from "../hooks/useAnomalyList";

function AnomalyListPage({ title, subtitle, isActive = 1, isStarred = null }) {
  const list = useAnomalyList({ isActive, isStarred });

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">{title}</h1>
          <p className="text-muted-foreground mt-1">{subtitle}</p>
        </div>
        <div className="text-right">
          <p className="text-3xl font-bold font-mono">{list.totalCount}</p>
          <p className="text-sm text-muted-foreground">matching anomalies</p>
        </div>
      </div>

      <SearchBar onQueryChange={list.handleQueryChange} />

      <AnomalyListFilters
        sortBy={list.sortBy}
        onSortChange={list.setSortBy}
        entitySelectValue={list.entitySelectValue}
        onEntityChange={list.handleEntityChange}
        atms={list.atms}
        servers={list.servers}
        anomalyTypeFilter={list.anomalyTypeFilter}
        onAnomalyTypeChange={list.setAnomalyTypeFilter}
        severityFilter={list.severityFilter}
        onSeverityChange={list.setSeverityFilter}
        detectorTypeFilter={list.detectorTypeFilter}
        onDetectorTypeChange={list.setDetectorTypeFilter}
        hasActiveFilters={list.hasActiveFilters}
        onClearFilters={list.clearFilters}
      />

      <AnomalyListResults
        loading={list.loading}
        fetchError={list.fetchError}
        pageAnomalies={list.pageAnomalies}
        formatTime={list.formatTime}
        onStar={list.handleStar}
        onCompleted={list.handleCompleted}
      />

      <AnomalyListPagination
        safePage={list.safePage}
        totalPages={list.totalPages}
        setCurrentPage={list.setCurrentPage}
      />
    </div>
  );
}

export default AnomalyListPage;
