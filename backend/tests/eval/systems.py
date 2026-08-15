"""System adapters for the RAG evaluation harness.

Runs every golden query through the three systems under comparison:

- baseline: plain rag_pipeline.process_query (single-shot RAG, top-k=5)
- hybrid:   agentic retrieval planning (deterministic planner) + post-loop generation
- agentic:  LLM-driven tool selection loop (agentic graph)

Tool wiring: the agent calls `adapter.get_langchain_tools()` through the
`backend.src.mcp.adapter` module, so we patch THAT module attribute with an
async factory of local StructuredTool wrappers (MCP-SSE is reachable at
mcp-server:8001 inside compose, host port 8002; in-process tools are used here
for eval speed and determinism). The patch must be applied BEFORE
`reset_graphs()`.
"""
from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

from langchain_core.tools import StructuredTool

from backend.src.mcp import adapter
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
from backend.src.rag.agent import reset_graphs, run_agent_query
from backend.src.rag.agent_types import AgentMode
from backend.src.rag.rag_pipeline import process_query
from backend.src.rag.retriever import reset_retriever

from .seed import _seed_chroma, _seed_db

TOP_K = 5  # shared retrieval depth for a fair baseline comparison
GOLDEN_SET_PATH = Path(__file__).parent / "golden_set.json"

SYSTEMS = ("baseline", "hybrid", "agentic")

_LOCAL_TOOLS: list[tuple[Callable, str, str]] = [
    (search_knowledge, "search_knowledge", "Search ATM log knowledge base"),
    (query_anomalies, "query_anomalies", "Query detected anomalies"),
    (get_anomaly, "get_anomaly", "Full detail for one anomaly by id"),
    (get_statistics, "get_statistics", "Aggregate anomaly statistics"),
    (get_atm_metrics, "get_atm_metrics", "Fetch ATM metrics"),
    (get_machine_history, "get_machine_history", "Fetch ATM event history"),
    (search_events, "search_events", "Raw event search by source/severity/time"),
    (get_error_context, "get_error_context", "Events sharing a correlation/transaction id"),
    (get_atm_info, "get_atm_info", "ATM registry info (OS, location)"),
    (compare_atms, "compare_atms", "Compare one ATM vs fleet aggregates"),
    (get_anomaly_class_info, "get_anomaly_class_info", "Canonical A1-A7 class knowledge"),
    (get_rag_collection_stats, "get_rag_collection_stats", "Knowledge base storage health"),
]


def build_local_tools() -> list[StructuredTool]:
    return [
        StructuredTool.from_function(func=fn, name=name, description=desc)
        for fn, name, desc in _LOCAL_TOOLS
    ]


async def _real_tools() -> list[StructuredTool]:
    return build_local_tools()


@dataclass
class SystemResult:
    system: str
    query_id: int
    query: str
    reference_answer: str
    answer: str
    retrieved_contexts: list[str] = field(default_factory=list)
    agent_trace: Optional[dict] = None
    error: Optional[str] = None


def _contexts(result: dict) -> list[str]:
    """Normalize any system result to the first TOP_K retrieved contexts."""
    sources = result.get("sources") or []
    return [s.get("text", "") for s in sources[:TOP_K]]


def run_baseline(golden: dict) -> SystemResult:
    try:
        result = process_query(
            query=golden["query"], atm_id=golden.get("atm_id"), top_k=TOP_K
        )
    except Exception as exc:  # pragma: no cover - defensive
        return SystemResult(
            "baseline", golden["id"], golden["query"], golden["reference_answer"],
            answer="", error=str(exc),
        )
    return SystemResult(
        "baseline",
        golden["id"],
        golden["query"],
        golden["reference_answer"],
        answer=result.get("answer", ""),
        retrieved_contexts=_contexts(result),
        error=result.get("error"),
    )


async def run_agent(golden: dict, mode: AgentMode) -> SystemResult:
    result = await run_agent_query(
        query=golden["query"],
        atm_id=golden.get("atm_id"),
        mode=mode,
        top_k=TOP_K,
    )
    return SystemResult(
        mode.value,
        golden["id"],
        golden["query"],
        golden["reference_answer"],
        answer=result.get("answer", ""),
        retrieved_contexts=_contexts(result),
        agent_trace=result.get("agent_trace"),
        error=result.get("error"),
    )


_seeded = False


def seed() -> None:
    """Load the deterministic fixtures this eval runs against (once per process)."""
    global _seeded
    if _seeded:
        return
    _seed_db()
    _seed_chroma()
    reset_retriever()  # drop cached collection UUID invalidated by delete+recreate
    _seeded = True


_patched = False


def _ensure_patched() -> None:
    """Patch adapter.get_langchain_tools + rebuild graphs once, before any query."""
    global _patched
    if _patched:
        return
    adapter.get_langchain_tools = _real_tools
    reset_graphs()
    _patched = True


def run_systems(golden_set: list[dict], systems: tuple[str, ...] = SYSTEMS) -> list[SystemResult]:
    """Run all golden queries through the requested systems. Seeds first."""
    seed()
    results: list[SystemResult] = []
    for golden in golden_set:
        if "baseline" in systems:
            results.append(run_baseline(golden))
    if "hybrid" in systems or "agentic" in systems:
        # Patch BEFORE any graph is built; agent calls adapter.get_langchain_tools.
        _ensure_patched()
        for golden in golden_set:
            if "hybrid" in systems:
                results.append(asyncio.run(run_agent(golden, AgentMode.HYBRID)))
            if "agentic" in systems:
                results.append(asyncio.run(run_agent(golden, AgentMode.AGENTIC)))
    return results


def main() -> None:
    import sys

    with open(GOLDEN_SET_PATH) as fh:
        golden_set = json.load(fh)
    systems = tuple(sys.argv[1:]) or SYSTEMS
    results = run_systems(golden_set, systems)
    print(f"ran {len(results)} system/query pairs: "
          f"{len([r for r in results if not r.error])} ok, "
          f"{len([r for r in results if r.error])} errored")


if __name__ == "__main__":
    main()