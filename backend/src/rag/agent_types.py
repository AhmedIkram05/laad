"""Shared types for the agentic / hybrid RAG paths."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class AgentMode(Enum):
    """How a query is answered: full agentic loop or deterministic hybrid."""

    AGENTIC = "agentic"
    HYBRID = "hybrid"


@dataclass
class ToolCallRecord:
    """One MCP tool invocation captured during an agent run."""

    tool: str
    args: dict
    round_index: int
    duration_s: float
    ok: bool
    char_len: int


@dataclass
class AgentTrace:
    """Runtime observability for one agent/hybrid query."""

    mode: str
    tool_calls: list = field(default_factory=list)
    rounds: int = 0
    model_calls: int = 0
    latencies: dict = field(default_factory=dict)
    selected_tools: list = field(default_factory=list)
    retries: int = 0
    retry_trigger: Optional[float] = None
    model_calls_truncated: bool = False