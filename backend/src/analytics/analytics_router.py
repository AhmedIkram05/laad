from __future__ import annotations
import logging
from fastapi import APIRouter, Query
from typing import Optional
from datetime import datetime, timedelta
from psycopg2.extras import RealDictCursor

from backend.src.database.connection import get_conn, release_conn

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/analytics", tags=["analytics"])


@router.get("/events")
def get_events_timeline(
    hours: int = Query(24, ge=1, le=168),
    bucket_minutes: int = Query(60, ge=5, le=1440),
    sources: Optional[str] = Query(None, description="Comma-separated sources: ATM_APP,HARDWARE,TERMINAL_HANDLER")
):
    """
    Returns time-bucketed event counts per source with anomaly markers.
    """
    conn = get_conn()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cutoff_time = datetime.now() - timedelta(hours=hours)
            bucket_seconds = bucket_minutes * 60

            source_list = []
            if sources:
                source_list = [s.strip().upper() for s in sources.split(",") if s.strip()]

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
                bucket_start = row['bucket_start']
                source = row['source']
                count = row['count']
                key = bucket_start.isoformat() if isinstance(bucket_start, datetime) else str(bucket_start)
                if key not in buckets:
                    buckets[key] = {"bucket_start": key, "sources": {}, "anomaly_markers": []}
                buckets[key]["sources"][source] = count

            anomaly_markers_by_bucket = {}
            for row in anomaly_rows:
                bucket_start = row['bucket_start']
                anomaly_type = row['anomaly_type']
                severity = row['severity']
                key = bucket_start.isoformat() if isinstance(bucket_start, datetime) else str(bucket_start)
                if key not in anomaly_markers_by_bucket:
                    anomaly_markers_by_bucket[key] = []
                anomaly_markers_by_bucket[key].append({
                    "type": anomaly_type,
                    "severity": severity
                })

            for key in buckets:
                if key in anomaly_markers_by_bucket:
                    buckets[key]["anomaly_markers"] = anomaly_markers_by_bucket[key]

            return {
                "time_series": list(buckets.values()),
                "parameters": {
                    "hours": hours,
                    "bucket_minutes": bucket_minutes,
                    "sources": source_list or ["ATM_APP", "HARDWARE", "TERMINAL_HANDLER"]
                }
            }

    except Exception as e:
        logger.error("Events analytics endpoint failed: %s", e, exc_info=True)
        return {"time_series": [], "error": str(e)}
    finally:
        release_conn(conn)


@router.get("/metrics")
def get_metrics_timeline(
    hours: int = Query(24, ge=1, le=168),
    bucket_minutes: int = Query(60, ge=5, le=1440),
    sources: Optional[str] = Query(None, description="Comma-separated sources: KAFKA,PROMETHEUS,OS,CLOUD")
):
    """
    Returns time-bucketed metric averages per source with anomaly markers.
    """
    conn = get_conn()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cutoff_time = datetime.now() - timedelta(hours=hours)
            bucket_seconds = bucket_minutes * 60

            source_list = []
            if sources:
                source_list = [s.strip().upper() for s in sources.split(",") if s.strip()]

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
                bucket_start = row['bucket_start']
                source = row['source']
                metric_name = row['metric_name']
                avg_value = float(row['avg_value']) if row['avg_value'] is not None else 0.0
                key = bucket_start.isoformat() if isinstance(bucket_start, datetime) else str(bucket_start)
                if key not in buckets:
                    buckets[key] = {"bucket_start": key, "metrics": {}, "anomaly_markers": []}
                if source not in buckets[key]["metrics"]:
                    buckets[key]["metrics"][source] = {}
                buckets[key]["metrics"][source][metric_name] = round(avg_value, 2)

            anomaly_markers_by_bucket = {}
            for row in anomaly_rows:
                bucket_start = row['bucket_start']
                anomaly_type = row['anomaly_type']
                severity = row['severity']
                key = bucket_start.isoformat() if isinstance(bucket_start, datetime) else str(bucket_start)
                if key not in anomaly_markers_by_bucket:
                    anomaly_markers_by_bucket[key] = []
                anomaly_markers_by_bucket[key].append({
                    "type": anomaly_type,
                    "severity": severity
                })

            for key in buckets:
                if key in anomaly_markers_by_bucket:
                    buckets[key]["anomaly_markers"] = anomaly_markers_by_bucket[key]

            return {
                "time_series": list(buckets.values()),
                "parameters": {
                    "hours": hours,
                    "bucket_minutes": bucket_minutes,
                    "sources": source_list or ["KAFKA", "PROMETHEUS", "OS", "CLOUD"]
                }
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
            return {
                "metrics": [row['metric_name'] for row in rows]
            }
    except Exception as e:
        logger.error("Metrics list endpoint failed: %s", e, exc_info=True)
        return {"metrics": [], "error": str(e)}
    finally:
        release_conn(conn)
