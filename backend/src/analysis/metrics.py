"""Metrics endpoint for anomaly analytics and dashboard visualization."""

from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
from psycopg2.extras import RealDictCursor
from backend.src.database.connection import get_conn, release_conn


def get_time_bucketed_anomalies(
    hours: int = 24,
    bucket_minutes: int = 60,
    anomaly_type: Optional[str] = None,
    severity: Optional[str] = None,
    is_active: Optional[int] = None
) -> List[Dict[str, Any]]:
    """
    Get anomaly counts grouped by time buckets.
    
    Args:
        hours: How many hours back to look (default: 24)
        bucket_minutes: Size of each time bucket in minutes (default: 60 = hourly)
        anomaly_type: Filter by specific anomaly type (A1-A7)
        severity: Filter by severity level
        is_active: Filter by active status (1=active, 0=resolved)
        
    Returns:
        List of dictionaries with bucket_start, bucket_end, and counts by type
    """
    conn = get_conn()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            # Build WHERE clause
            where_clauses = ["1=1"]
            params: List[Any] = []
            
            # Time filter
            cutoff_time = datetime.now() - timedelta(hours=hours)
            where_clauses.append("detected_at >= %s")
            params.append(cutoff_time)
            
            # Additional filters
            if anomaly_type:
                where_clauses.append("anomaly_type = %s")
                params.append(anomaly_type.upper())
                
            if severity:
                where_clauses.append("severity = %s")
                params.append(severity.upper())
                
            if is_active is not None:
                where_clauses.append("is_active = %s")
                params.append(is_active)
            
            where_sql = " AND ".join(where_clauses)
            
            # Time bucketing query — integer division floors epoch to bucket boundary
            bucket_seconds = bucket_minutes * 60
            query_sql = """
                WITH time_buckets AS (
                    SELECT 
                        to_timestamp(
                            (EXTRACT(EPOCH FROM detected_at)::int / %s) * %s
                        ) as bucket_start,
                        anomaly_type
                    FROM anomalies
                    WHERE """ + where_sql + """
                )
                SELECT 
                    bucket_start,
                    (bucket_start + %s * interval '1 second') as bucket_end,
                    anomaly_type,
                    COUNT(*) as count
                FROM time_buckets
                GROUP BY bucket_start, anomaly_type
                ORDER BY bucket_start
            """
            
            query_params = [bucket_seconds, bucket_seconds] + params + [bucket_seconds]
            cur.execute(query_sql, query_params)
            rows = cur.fetchall()
            
            # Process into time-series format
            if not rows:
                return []
                
            # Get all unique time buckets
            buckets = {}
            for row in rows:
                bucket_key = row['bucket_start']
                if bucket_key not in buckets:
                    buckets[bucket_key] = {
                        'bucket_start': row['bucket_start'],
                        'bucket_end': row['bucket_end'],
                        'total': 0
                    }
                
                # Initialize anomaly type counts if not present
                if 'types' not in buckets[bucket_key]:
                    buckets[bucket_key]['types'] = {}
                    
                buckets[bucket_key]['types'][row['anomaly_type']] = row['count']
                buckets[bucket_key]['total'] += row['count']
            
            # Convert to list format
            result = []
            for bucket_key in sorted(buckets.keys()):
                bucket = buckets[bucket_key]
                bucket_data = {
                    'bucket_start': bucket['bucket_start'].isoformat() if isinstance(bucket['bucket_start'], datetime) else bucket['bucket_start'],
                    'bucket_end': bucket['bucket_end'].isoformat() if isinstance(bucket['bucket_end'], datetime) else bucket['bucket_end'],
                    'total': bucket['total'],
                    'types': bucket.get('types', {})
                }
                result.append(bucket_data)
                
            return result
            
    finally:
        release_conn(conn)


def get_anomaly_summary() -> Dict[str, Any]:
    """
    Get summary statistics for anomaly dashboard.
    
    Returns:
        Dictionary with total counts, active/resolved, severity breakdown, etc.
    """
    conn = get_conn()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            # Get overall counts
            cur.execute("""
                SELECT 
                    COUNT(*) as total,
                    COUNT(*) FILTER (WHERE is_active = 1) as active,
                    COUNT(*) FILTER (WHERE is_active = 0) as resolved,
                    COUNT(*) FILTER (WHERE severity = 'CRITICAL') as critical,
                    COUNT(*) FILTER (WHERE severity = 'MAJOR') as major,
                    COUNT(*) FILTER (WHERE severity = 'HIGH') as high,
                    COUNT(*) FILTER (WHERE severity = 'WARNING') as warning
                FROM anomalies
            """)
            summary = dict(cur.fetchone())
            
            # Get breakdown by type
            cur.execute("""
                SELECT 
                    anomaly_type,
                    COUNT(*) as count,
                    COUNT(*) FILTER (WHERE is_active = 1) as active
                FROM anomalies
                GROUP BY anomaly_type
                ORDER BY anomaly_type
            """)
            type_breakdown = {}
            for row in cur.fetchall():
                type_breakdown[row['anomaly_type']] = {
                    'total': row['count'],
                    'active': row['active']
                }
            
            summary['by_type'] = type_breakdown
            
            # Get recent trend (last 24 hours hourly)
            cur.execute("""
                SELECT 
                    date_trunc('hour', detected_at) as hour,
                    COUNT(*) as count,
                    COUNT(*) FILTER (WHERE is_active = 1) as active
                FROM anomalies
                WHERE detected_at >= NOW() - INTERVAL '24 hours'
                GROUP BY date_trunc('hour', detected_at)
                ORDER BY hour
            """)
            
            hourly_trend = []
            for row in cur.fetchall():
                hourly_trend.append({
                    'hour': row['hour'].isoformat() if isinstance(row['hour'], datetime) else row['hour'],
                    'total': row['count'],
                    'active': row['active']
                })
            
            summary['hourly_trend'] = hourly_trend
            
            return summary
            
    finally:
        release_conn(conn)