"""Utility functions for RAG module."""

from __future__ import annotations

import logging
import re
from typing import Optional

logger = logging.getLogger(__name__)


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
    """Extract ATM ID from natural language query."""
    pattern = r"(ATM-GB-\d{4})"
    match = re.search(pattern, query, re.IGNORECASE)
    return match.group(1) if match else None


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