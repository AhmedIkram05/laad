"""Structured (SQL-backed) MCP tools: anomalies, events, metrics, statistics.

All database access goes through backend.src.database.connection.get_cursor() —
never raw psycopg2 here.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from backend.src.database.connection import get_cursor

_GROUP_BY_WHITELIST = {"anomaly_type", "atm_id", "severity"}


def _json_safe(row: dict) -> dict:
    """RealDictCursor rows carry datetime/Decimal — make them JSON-serializable."""
    out = {}
    for k, v in row.items():
        if isinstance(v, datetime):
            out[k] = v.isoformat()
        elif isinstance(v, Decimal):
            out[k] = float(v)
        else:
            out[k] = v
    return out


def _rows(cursor) -> list[dict]:
    return [_json_safe(dict(r)) for r in cursor.fetchall()]


def query_anomalies(
    atm_id: str | None = None,
    anomaly_type: str | None = None,
    severity: str | None = None,
    limit: int = 100,
    is_active: bool | None = None,
    start: str | None = None,
    end: str | None = None,
) -> dict:
    """List detected anomalies, newest first, with optional filters.

    Use when the user asks about anomalies, failures, faults or suspicious
    behavior on an ATM. Severity values in use: CRITICAL, ERROR, FATAL, WARNING,
    INFO (HIGH/MAJOR/LOW are not used and will match nothing). is_active filters
    open (1) vs resolved (0) anomalies. start/end are ISO-8601 timestamps.

    Args:
        atm_id: Scope to one ATM (e.g. ATM-GB-0001).
        anomaly_type: Anomaly class filter (A1..A7).
        severity: One of CRITICAL/ERROR/FATAL/WARNING/INFO.
        limit: Max rows (1-500, default 100).
        is_active: True for open anomalies only, False for resolved only.
        start: Include anomalies detected at/after this ISO timestamp.
        end: Include anomalies detected at/before this ISO timestamp.

    Returns:
        {"rows": [{"id","detected_at","anomaly_type","atm_id","severity","title",
                   "is_active","model_confidence_score"}], "count": N}
    """
    where, params = [], []
    if atm_id:
        where.append("atm_id = %s")
        params.append(atm_id)
    if anomaly_type:
        where.append("anomaly_type = %s")
        params.append(anomaly_type)
    if severity:
        where.append("severity = %s")
        params.append(severity)
    if is_active is not None:
        where.append("is_active = %s")
        params.append(1 if is_active else 0)
    if start:
        where.append("detected_at >= %s")
        params.append(start)
    if end:
        where.append("detected_at <= %s")
        params.append(end)
    sql = (
        "SELECT id, detected_at, anomaly_type, atm_id, severity, title, is_active, "
        "model_confidence_score FROM anomalies"
    )
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY detected_at DESC LIMIT %s"
    params.append(max(1, min(limit, 500)))
    with get_cursor() as cur:
        cur.execute(sql, params)
        rows = _rows(cur)
    return {"rows": rows, "count": len(rows)}


def get_anomaly(anomaly_id: str | int) -> dict:
    """Fetch the full detail of a single anomaly by its id.

    Use after query_anomalies when the user needs the full picture of one
    anomaly: explanation, recommended_action, sources_involved, correlation_id,
    transaction_id, feedback_rating, is_starred.

    Args:
        anomaly_id: The anomaly's numeric id.

    Returns:
        Full anomaly row, or {"error": "anomaly not found"}.
    """
    with get_cursor() as cur:
        cur.execute(
            "SELECT * FROM anomalies WHERE id = %s",
            (int(anomaly_id),),
        )
        row = cur.fetchone()
    if row is None:
        return {"error": f"anomaly {anomaly_id} not found"}
    return _json_safe(dict(row))


def get_machine_history(atm_id: str, hours: int = 24, limit: int = 200) -> dict:
    """Merged chronological timeline of an ATM: events + anomalies, newest first.

    Use for "what happened to this ATM recently" questions.

    Args:
        atm_id: The ATM id (e.g. ATM-GB-0001).
        hours: Look-back window (default 24).
        limit: Max rows (1-500, default 200).

    Returns:
        {"rows": [{"kind","id","timestamp","source","event_type","severity",
                   "description"}], "count": N}
    """
    hours = max(1, min(hours, 24 * 30))
    limit = max(1, min(limit, 500))
    sql = (
        "SELECT 'event' AS kind, id, timestamp, source, event_type, severity, "
        "message AS description FROM events "
        "WHERE atm_id = %s AND timestamp >= NOW() - %s::interval "
        "UNION ALL "
        "SELECT 'anomaly' AS kind, id, detected_at AS timestamp, 'ANOMALY' AS source, "
        "anomaly_type AS event_type, severity, title AS description FROM anomalies "
        "WHERE atm_id = %s AND detected_at >= NOW() - %s::interval "
        "ORDER BY timestamp DESC LIMIT %s"
    )
    with get_cursor() as cur:
        cur.execute(sql, (atm_id, f"{hours} hours", atm_id, f"{hours} hours", limit))
        rows = _rows(cur)
    return {"rows": rows, "count": len(rows)}


def get_atm_metrics(
    entity_id: str,
    metric_name: str | None = None,
    start: str | None = None,
    end: str | None = None,
    limit: int = 500,
) -> dict:
    """Time-series metric samples for a machine (or any monitored entity).

    Use for numeric questions (memory, CPU, latency, throughput...). Metric
    names include jvm_memory_used_bytes, process_cpu_usage, cpu_usage_percent,
    memory_usage_percent, network_errors, kafka_throughput, and container/*.

    Args:
        entity_id: The monitored entity id (ATM id for ATMs).
        metric_name: Optional metric name filter.
        start: Only samples at/after this ISO timestamp.
        end: Only samples at/before this ISO timestamp.
        limit: Max rows (1-1000, default 500).

    Returns:
        {"rows": [{"timestamp","metric_name","metric_value","source"}], "count": N}
    """
    where, params = ["entity_id = %s"], [entity_id]
    if metric_name:
        where.append("metric_name = %s")
        params.append(metric_name)
    if start:
        where.append("timestamp >= %s")
        params.append(start)
    if end:
        where.append("timestamp <= %s")
        params.append(end)
    sql = (
        "SELECT timestamp, metric_name, metric_value, source FROM metrics "
        "WHERE " + " AND ".join(where)
        + " ORDER BY timestamp DESC LIMIT %s"
    )
    params.append(max(1, min(limit, 1000)))
    with get_cursor() as cur:
        cur.execute(sql, params)
        rows = _rows(cur)
    return {"rows": rows, "count": len(rows)}


def get_statistics(
    hours: int | None = None,
    group_by: str = "anomaly_type",
    is_active: bool | None = None,
) -> dict:
    """Aggregate anomaly counts, grouped and with an active/resolved split.

    Use for "how many anomalies", "trends", "which type is most common".

    Args:
        hours: Optional look-back window; omit for all time.
        group_by: One of anomaly_type (default), atm_id, severity.
        is_active: True counts open anomalies only, False resolved only.

    Returns:
        {"groups": [{"group","count"}], "total": N, "active": N, "resolved": N}
    """
    if group_by not in _GROUP_BY_WHITELIST:
        return {"error": f"group_by must be one of {sorted(_GROUP_BY_WHITELIST)}"}
    where, params = [], []
    if hours:
        where.append("detected_at >= NOW() - %s::interval")
        params.append(f"{max(1, min(hours, 24 * 365))} hours")
    if is_active is not None:
        where.append("is_active = %s")
        params.append(1 if is_active else 0)
    clause = (" WHERE " + " AND ".join(where)) if where else ""
    with get_cursor() as cur:
        cur.execute(
            f"SELECT {group_by} AS group_key, COUNT(*) AS count FROM anomalies{clause} "
            "GROUP BY " + group_by + " ORDER BY count DESC",
            params,
        )
        groups = [{"group": r["group_key"], "count": r["count"]} for r in _rows(cur)]
        cur.execute(
            "SELECT COUNT(*) AS total, "
            "COALESCE(SUM(is_active), 0) AS active, "
            "COALESCE(SUM(1 - is_active), 0) AS resolved FROM anomalies" + clause,
            params,
        )
        totals = cur.fetchone()
    return {
        "groups": groups,
        "total": totals["total"],
        "active": totals["active"],
        "resolved": totals["resolved"],
    }


def search_events(
    source: str | None = None,
    atm_id: str | None = None,
    severity: str | None = None,
    start: str | None = None,
    end: str | None = None,
    limit: int = 200,
) -> dict:
    """Search raw system events (logs) with filters, newest first.

    Sources in use: ATM_APP, HARDWARE, TERMINAL_HANDLER, KAFKA, OS, PROMETHEUS,
    CLOUD. Messages are truncated to 500 chars.

    Args:
        source: Event source filter.
        atm_id: ATM scope filter.
        severity: One of ERROR/FATAL/WARNING/INFO/DEBUG.
        start: Only events at/after this ISO timestamp.
        end: Only events at/before this ISO timestamp.
        limit: Max rows (1-500, default 200).

    Returns:
        {"rows": [{"id","timestamp","source","atm_id","event_type","severity",
                   "message"}], "count": N}
    """
    where, params = [], []
    if source:
        where.append("source = %s")
        params.append(source)
    if atm_id:
        where.append("atm_id = %s")
        params.append(atm_id)
    if severity:
        where.append("severity = %s")
        params.append(severity)
    if start:
        where.append("timestamp >= %s")
        params.append(start)
    if end:
        where.append("timestamp <= %s")
        params.append(end)
    sql = (
        "SELECT id, timestamp, source, atm_id, event_type, severity, message FROM events "
        "WHERE " + (" AND ".join(where) if where else "TRUE")
        + " ORDER BY timestamp DESC LIMIT %s"
    )
    params.append(max(1, min(limit, 500)))
    with get_cursor() as cur:
        cur.execute(sql, params)
        rows = []
        for r in cur.fetchall():
            row = _json_safe(dict(r))
            if row.get("message") and len(row["message"]) > 500:
                row["message"] = row["message"][:500] + "..."
            rows.append(row)
    return {"rows": rows, "count": len(rows)}


def get_error_context(
    correlation_id: str | None = None,
    transaction_id: str | None = None,
    limit: int = 100,
) -> dict:
    """Return all events sharing a correlation or transaction id.

    Use to trace a failure across components. Exactly one of correlation_id or
    transaction_id must be provided.

    Args:
        correlation_id: Trace this correlation id.
        transaction_id: Trace this transaction id.
        limit: Max rows (1-500, default 100).

    Returns:
        {"rows": [event rows newest first], "count": N}
    """
    if not (correlation_id or transaction_id) or (correlation_id and transaction_id):
        return {"error": "exactly one of correlation_id or transaction_id required"}
    sql = (
        "SELECT id, timestamp, source, atm_id, event_type, severity, message FROM events "
        "WHERE correlation_id = %s OR transaction_id = %s "
        "ORDER BY timestamp DESC LIMIT %s"
    )
    key = correlation_id or transaction_id
    with get_cursor() as cur:
        cur.execute(sql, (key, key, max(1, min(limit, 500))))
        rows = _rows(cur)
    return {"rows": rows, "count": len(rows)}


def get_atm_info(atm_id: str) -> dict:
    """Registry info for one ATM: os_version and location_code.

    Args:
        atm_id: The ATM id (e.g. ATM-GB-0001).

    Returns:
        {"atm_id", "os_version", "location_code"} or {"error": "ATM not found"}.
    """
    with get_cursor() as cur:
        cur.execute("SELECT os_version, location_code FROM atms WHERE atm_id = %s", (atm_id,))
        row = cur.fetchone()
    if row is None:
        return {"error": f"ATM {atm_id} not found in registry"}
    return {"atm_id": atm_id, **dict(row)}


def compare_atms(
    metric_name: str | None = None,
    anomaly_type: str | None = None,
    hours: int = 24,
    limit: int = 20,
) -> dict:
    """Cross-ATM comparison: per-ATM aggregates plus fleet mean/std and outliers.

    Use for "compare ATMs", "which ATM is worst", fleet-wide questions. Pass
    metric_name to compare a metric (e.g. jvm_memory_used_bytes) or
    anomaly_type to compare anomaly counts per class.

    Args:
        metric_name: Metric to compare across ATMs (mutually exclusive with anomaly_type).
        anomaly_type: Anomaly class to compare counts for.
        hours: Look-back window (default 24).
        limit: Max ATMs (1-100, default 20).

    Returns:
        {"rows": [per-ATM aggregates], "overall_mean", "overall_std",
         "outliers": [atm_ids beyond mean + 2*std]}
    """
    hours = max(1, min(hours, 24 * 365))
    limit = max(1, min(limit, 100))
    interval = f"{hours} hours"
    if metric_name:
        sql = (
            "SELECT entity_id AS atm_id, COUNT(*) AS sample_count, "
            "AVG(metric_value) AS avg_value FROM metrics "
            "WHERE metric_name = %s AND timestamp >= NOW() - %s::interval "
            "GROUP BY entity_id ORDER BY avg_value DESC LIMIT %s"
        )
        params = (metric_name, interval, limit)
    else:
        sql = (
            "SELECT atm_id, COUNT(*) AS anomaly_count, "
            "AVG(model_confidence_score) AS avg_confidence FROM anomalies "
            "WHERE detected_at >= NOW() - %s::interval "
            + ("AND anomaly_type = %s " if anomaly_type else "")
            + "GROUP BY atm_id ORDER BY anomaly_count DESC LIMIT %s"
        )
        params = [interval] + ([anomaly_type] if anomaly_type else []) + [limit]
    with get_cursor() as cur:
        cur.execute(sql, params)
        rows = _rows(cur)
    values = []
    for r in rows:
        values.append(r.get("avg_value") if metric_name else r["anomaly_count"])
    mean = sum(values) / len(values) if values else 0.0
    std = (sum((v - mean) ** 2 for v in values) / len(values)) ** 0.5 if values else 0.0
    outliers = (
        [r["atm_id"] for r, v in zip(rows, values) if std > 0 and v > mean + 2 * std]
        if values
        else []
    )
    return {"rows": rows, "overall_mean": round(mean, 3), "overall_std": round(std, 3), "outliers": outliers}