"""Curated knowledge + collection-info tools (deterministic, no DB)."""

from __future__ import annotations

from backend.src.rag.retriever import get_retriever

# Curated anomaly-class knowledge. Deterministic — no LLM involved.
_ANOMALY_CLASSES = {
    "A1": {
        "name": "Hardware Failure",
        "description": "Physical hardware component failure (card reader, dispenser, sensors).",
        "typical_sources": ["HARDWARE", "ATM_APP"],
        "symptoms": ["component error codes", "device offline", "repeated retries"],
        "recommended_action": "Dispatch field engineer; check component diagnostics and part inventory.",
    },
    "A2": {
        "name": "Software Crash",
        "description": "Application-level crash, exception storm or process restart.",
        "typical_sources": ["ATM_APP", "OS"],
        "symptoms": ["exception traces", "process restarts", "startup failures"],
        "recommended_action": "Collect crash logs and traceback; correlate with deployment window.",
    },
    "A3": {
        "name": "Network Issue",
        "description": "Connectivity degradation or loss between ATM and backend.",
        "typical_sources": ["OS", "PROMETHEUS"],
        "symptoms": ["packet loss", "timeouts", "connection resets"],
        "recommended_action": "Check link status, firewall and TLS config; ping and traceroute from ATM.",
    },
    "A4": {
        "name": "Cash Management",
        "description": "Cash-related discrepancy: dispense errors, cassette issues, currency mismatch.",
        "typical_sources": ["ATM_APP", "TERMINAL_HANDLER"],
        "symptoms": ["dispense failures", "cassette alarms", "count mismatch"],
        "recommended_action": "Reconcile cassette counts; run dispense self-test before redeploying cash.",
    },
    "A5": {
        "name": "Security Incident",
        "description": "Potential fraud, tampering, skimming or unauthorized access indicators.",
        "typical_sources": ["ATM_APP", "CLOUD"],
        "symptoms": ["failed auth bursts", "tamper events", "unusual access patterns"],
        "recommended_action": "Escalate to security; freeze affected services; preserve evidence logs.",
    },
    "A6": {
        "name": "Configuration Drift",
        "description": "ATM configuration differs from the expected/policy baseline.",
        "typical_sources": ["CLOUD", "ATM_APP"],
        "symptoms": ["version mismatch", "config hash change", "policy violations"],
        "recommended_action": "Re-apply golden config; verify version pinning and change-control records.",
    },
    "A7": {
        "name": "Out-of-Order / Malformed Sequence",
        "description": "Events arriving out of order or malformed (includes A7_OUT_OF_ORDER and A7_MALFORMED sub-tags).",
        "typical_sources": ["KAFKA", "ATM_APP"],
        "symptoms": ["sequence gaps", "schema violations", "duplicate or stale events"],
        "recommended_action": "Check producer/consumer offsets; validate payload schema; replay from last good offset.",
    },
}


def get_anomaly_class_info(anomaly_class: str) -> dict:
    """Return curated knowledge about an anomaly class (A1..A7).

    Use to enrich answers with class-level context: what the class means, its
    typical sources, symptoms and the recommended action.

    Args:
        anomaly_class: One of A1..A7.

    Returns:
        {"anomaly_class", "name", "description", "typical_sources", "symptoms",
         "recommended_action"} or {"error": "unknown anomaly class"}.
    """
    info = _ANOMALY_CLASSES.get(anomaly_class.upper())
    if info is None:
        return {"error": f"unknown anomaly class {anomaly_class!r}; expected A1..A7"}
    return {"anomaly_class": anomaly_class.upper(), **info}


def get_rag_collection_stats() -> dict:
    """Return vector-store collection stats: total chunks and collection name.

    Useful for "how much data is indexed" questions and for sanity-checking
    retrieval coverage.

    Returns:
        {"total_chunks": N, "collection_name": "..."} or {"error": "..."}.
    """
    retriever = get_retriever()
    if retriever is None:
        return {"error": "vector store unavailable"}
    return retriever.get_collection_stats()
