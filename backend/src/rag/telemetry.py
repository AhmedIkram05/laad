"""Runtime telemetry for the agentic RAG retrofit (D15 / plan §4.1).

TraceRecord aggregates per-request agent-loop telemetry plus token/cost
estimates; record_trace persists it to rag_agent_traces (ADR-0003: AgentTrace
stays the in-process source of truth and feeds the API response). The
distributed view is OpenTelemetry spans (rag.query root, rag.tool.* children,
cap/gate events) — there is deliberately only one span representation, the
old OTEL_JSONL side-channel was retired in the Phase 3 rollout.
report.py --runtime renders the same shapes from these rows.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Optional

from backend.src.database.connection import get_cursor

logger = logging.getLogger(__name__)

# per-LLM-call pricing constant for est. cost (plan §7.3 / report.py)
COST_PER_CALL = 0.0004


@dataclass
class TraceRecord:
    """One agent-loop run: trace fields + token/cost estimates."""

    mode: Optional[str] = None
    rounds: int = 0
    model_calls: int = 0
    tool_calls: list[dict] = field(default_factory=list)
    latencies: dict = field(default_factory=dict)
    selected_tools: list[str] = field(default_factory=list)
    retries: int = 0
    retry_trigger: Optional[float] = None
    model_calls_truncated: bool = False
    tokens_in: int = 0
    tokens_out: int = 0

    @property
    def est_cost(self) -> float:
        return self.model_calls * COST_PER_CALL

    def to_dict(self) -> dict:
        return {
            "mode": self.mode,
            "rounds": self.rounds,
            "model_calls": self.model_calls,
            "tool_calls": self.tool_calls,
            "latencies": self.latencies,
            "selected_tools": self.selected_tools,
            "retries": self.retries,
            "retry_trigger": self.retry_trigger,
            "model_calls_truncated": self.model_calls_truncated,
            "tokens_in": self.tokens_in,
            "tokens_out": self.tokens_out,
            "est_cost": self.est_cost,
        }


def _from_trace(trace: dict) -> TraceRecord:
    return TraceRecord(
        mode=trace.get("mode"),
        rounds=trace.get("rounds", 0),
        model_calls=trace.get("model_calls", 0),
        tool_calls=trace.get("tool_calls", []),
        latencies=trace.get("latencies", {}),
        selected_tools=trace.get("selected_tools", []),
        retries=trace.get("retries", 0),
        retry_trigger=trace.get("retry_trigger"),
        model_calls_truncated=trace.get("model_calls_truncated", False),
    )


def record_trace(query_id: Optional[int], trace: Optional[dict]) -> None:
    """Persist one agent-loop trace to rag_agent_traces."""
    if query_id is None or not trace:
        return
    record = _from_trace(trace)
    try:
        with get_cursor(commit=True) as cur:
            cur.execute(
                """
                INSERT INTO rag_agent_traces
                (query_id, mode, rounds, model_calls, tool_calls, latencies,
                 selected_tools, retries, retry_trigger, model_calls_truncated)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    query_id,
                    record.mode,
                    record.rounds,
                    record.model_calls,
                    json.dumps(record.tool_calls),
                    json.dumps(record.latencies),
                    json.dumps(record.selected_tools),
                    record.retries,
                    record.retry_trigger,
                    record.model_calls_truncated,
                ),
            )
    except Exception as e:  # noqa: BLE001 - telemetry must never break the request
        logger.warning(f"Failed to save agent trace: {e}")


def aggregate(records: list[TraceRecord]) -> dict[str, float]:
    """Aggregate a batch of trace records (§4.1)."""
    n = len(records)
    if n == 0:
        return {}
    return {
        "traces": n,
        "mean_rounds": sum(r.rounds for r in records) / n,
        "mean_model_calls": sum(r.model_calls for r in records) / n,
        "total_est_cost": sum(r.est_cost for r in records),
        "truncated_count": sum(1 for r in records if r.model_calls_truncated),
    }
