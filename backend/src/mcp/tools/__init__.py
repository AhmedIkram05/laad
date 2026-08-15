"""MCP tool registry — every tool exposed by the LAAD MCP server."""
from backend.src.mcp.tools.knowledge import (
    get_anomaly_class_info,
    get_rag_collection_stats,
)
from backend.src.mcp.tools.structured import (
    compare_atms,
    get_anomaly,
    get_atm_info,
    get_atm_metrics,
    get_error_context,
    get_machine_history,
    get_statistics,
    query_anomalies,
    search_events,
)
from backend.src.mcp.tools.vector import search_knowledge

ALL_TOOLS = [
    search_knowledge,
    query_anomalies,
    get_anomaly,
    get_machine_history,
    get_atm_metrics,
    get_statistics,
    search_events,
    get_error_context,
    get_atm_info,
    compare_atms,
    get_anomaly_class_info,
    get_rag_collection_stats,
]

__all__ = ["ALL_TOOLS"]