"""Utility functions for RAG module."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from enum import Enum
from typing import Optional

logger = logging.getLogger(__name__)


class QueryType(Enum):
    """Types of queries the RAG system can handle."""
    STATS = "stats"
    DIAGNOSTIC = "diagnostic"
    TROUBLESHOOTING = "troubleshooting"
    GENERAL = "general"


@dataclass
class QueryIntent:
    """Parsed intent from user query."""
    error_only: bool = False
    most_recent_first: bool = False


def detect_query_intent(query: str) -> QueryIntent:
    """Detect user intent from query to optimize retrieval.
    
    Detects:
    - error_only: Query mentions issues/errors/problems → filter for ERROR/FATAL
    - most_recent_first: Query asks for recent/latest issues → sort by timestamp
    """
    query_lower = query.lower()
    
    error_keywords = [
        "issue", "issues", "error", "errors", "problem", "problems",
        "failure", "failures", "anomaly", "anomalies", "crash", "crashed",
        "down", "offline", "out of service", "failed", "fatal",
        "critical", "warning", "exception", "timeout", "disconnect",
    ]
    
    recent_keywords = [
        "most recent", "latest", "recent", "last", "newest", 
        "current", "today", "yesterday", "last hour", "last 6 hours",
    ]
    
    error_only = any(kw in query_lower for kw in error_keywords)
    most_recent_first = any(kw in query_lower for kw in recent_keywords)
    
    return QueryIntent(error_only=error_only, most_recent_first=most_recent_first)


def classify_query_type(query: str) -> QueryType:
    """Classify query type to route to appropriate handler.
    
    Detects:
    - stats: Questions asking for counts, totals, numbers (how many, count, total, list all)
    - diagnostic: Questions asking about what's wrong, why, root cause analysis
    - troubleshooting: Questions asking how to fix, what to do, solutions
    - general: Everything else (summaries, explanations, casual queries)
    """
    query_lower = query.lower()
    
    stats_keywords = [
        "how many", "how much", "count of", "number of", "total",
        "list all", "show me the", "what is the total", "sum",
        "quantity", "how many", "statistics", "stats", "dashboard",
    ]
    
    troubleshooting_keywords = [
        "how to fix", "how to resolve", "what to do", "how do i",
        "fix the", "solve the", "solution for", "resolve",
        "repair", "recover", "restore", "troubleshoot",
        "steps to", "guide", "instructions",
    ]
    
    diagnostic_keywords = [
        "what's wrong", "what is wrong", "why is", "why are",
        "what caused", "root cause", "reason for", "what's causing",
        "diagnose", "analysis", "investigate", "find the issue",
        "what issue", "what problem", "issue with", "problem with",
    ]
    
    for kw in stats_keywords:
        if kw in query_lower:
            return QueryType.STATS
    
    for kw in troubleshooting_keywords:
        if kw in query_lower:
            return QueryType.TROUBLESHOOTING
    
    for kw in diagnostic_keywords:
        if kw in query_lower:
            return QueryType.DIAGNOSTIC
    
    return QueryType.GENERAL


def sanitize_query(query: str) -> str:
    """Sanitize user query to prevent prompt injection."""
    dangerous_patterns = [
        r"ignore\s+(previous|above|all)\s+(instructions?|rules?|prompt)",
        r"system\s*:\s*",
        r"<\s*system\s*>",
        r"you\s+are\s+(now|假装)",
        r"forget\s+(everything|all|your)",
    ]

    sanitized = query
    for pattern in dangerous_patterns:
        sanitized = re.sub(pattern, "[FILTERED]", sanitized, flags=re.IGNORECASE)

    return sanitized.strip()


def extract_atm_id_from_query(query: str) -> Optional[str]:
    """Extract ATM ID from natural language query.
    
    Supports multiple formats:
    - ATM-GB-0001 (exact)
    - ATM 1, ATM 01 -> ATM-GB-0001
    - ATM-0001 -> ATM-GB-0001
    """
    query_upper = query.upper()
    
    exact_pattern = r"(ATM-GB-\d{4})"
    match = re.search(exact_pattern, query_upper)
    if match:
        return match.group(1)
    
    shorthand_pattern = r"ATM[-_\s]?(\d{1,2})(?:\s|$|[,:;.])"
    match = re.search(shorthand_pattern, query_upper)
    if match:
        num = int(match.group(1))
        if 1 <= num <= 10:
            return f"ATM-GB-{num:04d}"
    
    legacy_pattern = r"ATM-(\d{4})"
    match = re.search(legacy_pattern, query_upper)
    if match:
        num = int(match.group(1))
        if 1 <= num <= 10:
            return f"ATM-GB-{num:04d}"
    
    return None


def format_log_snippet(text: str, max_length: int = 200) -> str:
    """Format log text snippet for display."""
    if len(text) <= max_length:
        return text

    return text[:max_length].rsplit(" ", 1)[0] + "..."


def parse_confidence_level(score: float) -> str:
    """Parse numerical confidence to level."""
    if score >= 0.8:
        return "high"
    elif score >= 0.5:
        return "medium"
    else:
        return "low"


def truncate_for_display(text: str, max_lines: int = 5) -> str:
    """Truncate text to max lines for display."""
    lines = text.split("\n")
    if len(lines) <= max_lines:
        return text
    return "\n".join(lines[:max_lines]) + f"\n... ({len(lines) - max_lines} more lines)"