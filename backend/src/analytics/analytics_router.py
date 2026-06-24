from __future__ import annotations
import logging
from fastapi import APIRouter, Query
from typing import Optional
from datetime import datetime, timedelta, timezone
from psycopg2.extras import RealDictCursor

from backend.src.database.connection import get_conn, release_conn
from backend.src.cache import get_redis_client

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/analytics", tags=["analytics"])

EVENT_COUNTER_PREFIX = "stats:events:"
ANOMALY_COUNTER_PREFIX = "stats:anomaly:"
UNIQUE_ATMS_KEY = "stats:unique:atms"


@router.get("/events")
def get_events_timeline(
    hours: int = Query(24, ge=0, le=168),
    bucket_minutes: int = Query(60, ge=5, le=1440),
    sources: Optional[str] = Query(
        None, description="Comma-separated sources: ATM_APP,HARDWARE,TERMINAL_HANDLER"
    ),
):
    """
    Returns time-bucketed event counts per source with anomaly markers.
    """
    conn = get_conn()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cutoff_time = (
                datetime(2000, 1, 1, tzinfo=timezone.utc)
                if hours == 0
                else datetime.now(timezone.utc) - timedelta(hours=hours)
            )
            bucket_seconds = bucket_minutes * 60

            source_list = []
            if sources:
                source_list = [
                    s.strip().upper() for s in sources.split(",") if s.strip()
                ]

            if source_list:
                placeholders = ",".join(["%s"] * len(source_list))
                source_filter = f"AND source IN ({placeholders})"
            else:
                source_filter = ""
                source_list = []

            params = [bucket_seconds, bucket_seconds, cutoff_time] + source_list

            events_query = f"""
                WITH time_buckets AS (
                    SELECT
                        to_timestamp(
                            (EXTRACT(EPOCH FROM timestamp)::int / %s) * %s
                        ) as bucket_start,
                        source
                    FROM events
                    WHERE timestamp >= %s {source_filter}
                )
                SELECT
                    bucket_start,
                    source,
                    COUNT(*) as count
                FROM time_buckets
                GROUP BY bucket_start, source
                ORDER BY bucket_start, source
            """
            cur.execute(events_query, params)
            event_rows = cur.fetchall()

            anomaly_params = [bucket_seconds, bucket_seconds, cutoff_time]
            anomalies_query = """
                SELECT
                    to_timestamp(
                        (EXTRACT(EPOCH FROM detected_at)::int / %s) * %s
                    ) as bucket_start,
                    anomaly_type,
                    severity
                FROM anomalies
                WHERE detected_at >= %s
            """
            cur.execute(anomalies_query, anomaly_params)
            anomaly_rows = cur.fetchall()

            buckets = {}
            for row in event_rows:
                bucket_start = row["bucket_start"]
                source = row["source"]
                count = row["count"]
                key = (
                    bucket_start.isoformat()
                    if isinstance(bucket_start, datetime)
                    else str(bucket_start)
                )
                if key not in buckets:
                    buckets[key] = {
                        "bucket_start": key,
                        "sources": {},
                        "anomaly_markers": [],
                    }
                buckets[key]["sources"][source] = count

            anomaly_markers_by_bucket = {}
            for row in anomaly_rows:
                bucket_start = row["bucket_start"]
                anomaly_type = row["anomaly_type"]
                severity = row["severity"]
                key = (
                    bucket_start.isoformat()
                    if isinstance(bucket_start, datetime)
                    else str(bucket_start)
                )
                if key not in anomaly_markers_by_bucket:
                    anomaly_markers_by_bucket[key] = []
                anomaly_markers_by_bucket[key].append(
                    {"type": anomaly_type, "severity": severity}
                )

            for key in buckets:
                if key in anomaly_markers_by_bucket:
                    buckets[key]["anomaly_markers"] = anomaly_markers_by_bucket[key]

            return {
                "time_series": list(buckets.values()),
                "parameters": {
                    "hours": hours,
                    "bucket_minutes": bucket_minutes,
                    "sources": source_list
                    or ["ATM_APP", "HARDWARE", "TERMINAL_HANDLER"],
                },
            }

    except Exception as e:
        logger.error("Events analytics endpoint failed: %s", e, exc_info=True)
        return {"time_series": [], "error": str(e)}
    finally:
        release_conn(conn)


@router.get("/metrics")
def get_metrics_timeline(
    hours: int = Query(24, ge=0, le=168),
    bucket_minutes: int = Query(60, ge=5, le=1440),
    sources: Optional[str] = Query(
        None, description="Comma-separated sources: KAFKA,PROMETHEUS,OS,CLOUD"
    ),
):
    """
    Returns time-bucketed metric averages per source with anomaly markers.
    """
    conn = get_conn()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cutoff_time = (
                datetime(2000, 1, 1, tzinfo=timezone.utc)
                if hours == 0
                else datetime.now(timezone.utc) - timedelta(hours=hours)
            )
            bucket_seconds = bucket_minutes * 60

            source_list = []
            if sources:
                source_list = [
                    s.strip().upper() for s in sources.split(",") if s.strip()
                ]

            if source_list:
                placeholders = ",".join(["%s"] * len(source_list))
                source_filter = f"AND source IN ({placeholders})"
            else:
                source_filter = ""
                source_list = []

            params = [bucket_seconds, bucket_seconds, cutoff_time] + source_list

            metrics_query = f"""
                WITH time_buckets AS (
                    SELECT
                        to_timestamp(
                            (EXTRACT(EPOCH FROM timestamp)::int / %s) * %s
                        ) as bucket_start,
                        source,
                        metric_name,
                        AVG(metric_value) as avg_value
                    FROM metrics
                    WHERE timestamp >= %s {source_filter}
                    GROUP BY bucket_start, source, metric_name
                )
                SELECT
                    bucket_start,
                    source,
                    metric_name,
                    avg_value
                FROM time_buckets
                ORDER BY bucket_start, source, metric_name
            """
            cur.execute(metrics_query, params)
            metric_rows = cur.fetchall()

            anomaly_params = [bucket_seconds, bucket_seconds, cutoff_time]
            anomalies_query = """
                SELECT
                    to_timestamp(
                        (EXTRACT(EPOCH FROM detected_at)::int / %s) * %s
                    ) as bucket_start,
                    anomaly_type,
                    severity
                FROM anomalies
                WHERE detected_at >= %s
            """
            cur.execute(anomalies_query, anomaly_params)
            anomaly_rows = cur.fetchall()

            buckets = {}
            for row in metric_rows:
                bucket_start = row["bucket_start"]
                source = row["source"]
                metric_name = row["metric_name"]
                avg_value = (
                    float(row["avg_value"]) if row["avg_value"] is not None else 0.0
                )
                key = (
                    bucket_start.isoformat()
                    if isinstance(bucket_start, datetime)
                    else str(bucket_start)
                )
                if key not in buckets:
                    buckets[key] = {
                        "bucket_start": key,
                        "metrics": {},
                        "anomaly_markers": [],
                    }
                if source not in buckets[key]["metrics"]:
                    buckets[key]["metrics"][source] = {}
                buckets[key]["metrics"][source][metric_name] = round(avg_value, 2)

            anomaly_markers_by_bucket = {}
            for row in anomaly_rows:
                bucket_start = row["bucket_start"]
                anomaly_type = row["anomaly_type"]
                severity = row["severity"]
                key = (
                    bucket_start.isoformat()
                    if isinstance(bucket_start, datetime)
                    else str(bucket_start)
                )
                if key not in anomaly_markers_by_bucket:
                    anomaly_markers_by_bucket[key] = []
                anomaly_markers_by_bucket[key].append(
                    {"type": anomaly_type, "severity": severity}
                )

            for key in buckets:
                if key in anomaly_markers_by_bucket:
                    buckets[key]["anomaly_markers"] = anomaly_markers_by_bucket[key]

            return {
                "time_series": list(buckets.values()),
                "parameters": {
                    "hours": hours,
                    "bucket_minutes": bucket_minutes,
                    "sources": source_list or ["KAFKA", "PROMETHEUS", "OS", "CLOUD"],
                },
            }

    except Exception as e:
        logger.error("Metrics analytics endpoint failed: %s", e, exc_info=True)
        return {"time_series": [], "error": str(e)}
    finally:
        release_conn(conn)


@router.get("/metrics/list")
def get_available_metrics():
    """
    Returns list of unique metric names available in the database.
    """
    conn = get_conn()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT DISTINCT metric_name
                FROM metrics
                ORDER BY metric_name
            """)
            rows = cur.fetchall()
            return {"metrics": [row["metric_name"] for row in rows]}
    except Exception as e:
        logger.error("Metrics list endpoint failed: %s", e, exc_info=True)
        return {"metrics": [], "error": str(e)}
    finally:
        release_conn(conn)


def increment_event_counter(source: str, hour: str) -> None:
    """Increment the event counter for a source in a given hour bucket."""
    client = get_redis_client()
    if client is None:
        return
    try:
        key = f"{EVENT_COUNTER_PREFIX}{source}:{hour}"
        client.incr(key)
        client.expire(key, 86400 * 7)
    except Exception as e:
        logger.warning(f"Failed to increment event counter: {e}")


def increment_anomaly_counter(anomaly_type: str, hour: str) -> None:
    """Increment the anomaly counter for a type in a given hour bucket."""
    client = get_redis_client()
    if client is None:
        return
    try:
        key = f"{ANOMALY_COUNTER_PREFIX}type:{hour}"
        client.zincrby(key, 1, anomaly_type)
        client.expire(key, 86400 * 7)
    except Exception as e:
        logger.warning(f"Failed to increment anomaly counter: {e}")


def track_unique_atm(atm_id: str) -> None:
    """Add an ATM ID to the HyperLogLog for unique ATM cardinality."""
    client = get_redis_client()
    if client is None:
        return
    try:
        client.pfadd(UNIQUE_ATMS_KEY, atm_id)
        client.expire(UNIQUE_ATMS_KEY, 86400 * 30)
    except Exception as e:
        logger.warning(f"Failed to track unique ATM: {e}")


def get_unique_atm_count() -> int:
    """Get the unique ATM count from HyperLogLog."""
    client = get_redis_client()
    if client is None:
        return 0
    try:
        return client.pfcount(UNIQUE_ATMS_KEY)
    except Exception as e:
        logger.warning(f"Failed to get unique ATM count: {e}")
        return 0


@router.get("/stats/realtime")
def get_realtime_stats(
    hours: int = Query(24, ge=0, le=168),
):
    """Get real-time analytics stats from Redis counters.

    Returns event counts by source, anomaly type frequency, and unique ATM count.
    Falls back to PostgreSQL queries when Redis counters are empty or unavailable.
    When hours=0, returns all-time stats directly from the database.
    """
    client = get_redis_client()
    events_by_source = {}
    anomaly_types = {}
    unique_atms = 0

    all_time = hours == 0

    # For time-bounded queries, try Redis counters first
    if not all_time and client is not None:
        try:
            cutoff_time = datetime.now(timezone.utc) - timedelta(hours=hours)
            event_keys = client.keys(f"{EVENT_COUNTER_PREFIX}*")
            for key in event_keys:
                value = client.get(key)
                if value:
                    parts = key.replace(EVENT_COUNTER_PREFIX, "").split(":")
                    source = parts[0]
                    # Filter by hour bucket from key: stats:events:{source}:{hour}
                    if len(parts) > 1:
                        try:
                            key_hour = datetime.strptime(
                                parts[1], "%Y-%m-%dT%H"
                            ).replace(tzinfo=timezone.utc)
                            if cutoff_time and key_hour < cutoff_time:
                                continue
                        except ValueError:
                            continue
                    events_by_source[source] = events_by_source.get(source, 0) + int(
                        value
                    )

            anomaly_keys = client.keys(f"{ANOMALY_COUNTER_PREFIX}type:*")
            for key in anomaly_keys:
                # Filter by hour bucket from key: stats:anomaly:type:{hour}
                hour_str = key.replace(f"{ANOMALY_COUNTER_PREFIX}type:", "")
                try:
                    key_hour = datetime.strptime(hour_str, "%Y-%m-%dT%H").replace(
                        tzinfo=timezone.utc
                    )
                    if cutoff_time and key_hour < cutoff_time:
                        continue
                except ValueError:
                    continue
                entries = client.zrange(key, 0, -1, withscores=True)
                for atype, score in entries:
                    anomaly_types[atype] = anomaly_types.get(atype, 0) + int(score)
        except Exception as e:
            logger.warning(f"Redis stats failed, falling back to DB: {e}")

    # DB fallback: all-time query or when Redis returned nothing
    if all_time or not events_by_source:
        cutoff = (
            datetime.now(timezone.utc) - timedelta(hours=hours)
            if not all_time
            else None
        )
        conn = get_conn()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                if cutoff is not None:
                    cur.execute(
                        "SELECT source, COUNT(*) as cnt FROM events WHERE timestamp >= %s GROUP BY source",
                        (cutoff,),
                    )
                else:
                    cur.execute(
                        "SELECT source, COUNT(*) as cnt FROM events GROUP BY source",
                    )
                for row in cur.fetchall():
                    events_by_source[row["source"]] = (
                        events_by_source.get(row["source"], 0) + row["cnt"]
                    )

                # Also count metric sources (increment_event_counter is called from both event and metric handlers)
                if cutoff is not None:
                    cur.execute(
                        "SELECT source, COUNT(*) as cnt FROM metrics WHERE timestamp >= %s GROUP BY source",
                        (cutoff,),
                    )
                else:
                    cur.execute(
                        "SELECT source, COUNT(*) as cnt FROM metrics GROUP BY source",
                    )
                for row in cur.fetchall():
                    events_by_source[row["source"]] = (
                        events_by_source.get(row["source"], 0) + row["cnt"]
                    )

                if cutoff is not None:
                    cur.execute(
                        "SELECT anomaly_type, COUNT(*) as cnt FROM anomalies WHERE detected_at >= %s GROUP BY anomaly_type",
                        (cutoff,),
                    )
                else:
                    cur.execute(
                        "SELECT anomaly_type, COUNT(*) as cnt FROM anomalies GROUP BY anomaly_type",
                    )
                for row in cur.fetchall():
                    anomaly_types[row["anomaly_type"]] = row["cnt"]
        except Exception as e:
            logger.error(f"DB fallback for realtime stats failed: {e}", exc_info=True)
        finally:
            release_conn(conn)

    # Always count total monitored entities (ATMs + Servers) from the atms table
    conn = None
    try:
        conn = get_conn()
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT COUNT(*) as cnt FROM atms")
            row = cur.fetchone()
            unique_atms = row["cnt"] if row else 0
    except Exception as e:
        logger.error(f"Failed to count monitored entities: {e}", exc_info=True)
    finally:
        if conn is not None:
            release_conn(conn)

    return {
        "events_by_source": events_by_source,
        "anomaly_types": anomaly_types,
        "unique_atms": unique_atms,
    }


@router.get("/entities")
def list_entities():
    """Return all ATM and server entity IDs from the atms table."""
    conn = get_conn()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                "SELECT atm_id, os_version, location_code FROM atms ORDER BY atm_id"
            )
            rows = cur.fetchall()
        return {"entities": [dict(r) for r in rows]}
    except Exception as e:
        logger.error(f"Failed to fetch entities: {e}", exc_info=True)
        return {"entities": []}
    finally:
        release_conn(conn)
