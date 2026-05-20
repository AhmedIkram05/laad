"""Anomalies router.

Endpoints:
    GET   /anomalies                    — paginated, filterable anomaly list (supports grouping)
    PATCH /anomalies/{id}/resolve       — mark anomaly inactive
    PATCH /anomalies/{id}/star          — toggle starred
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from psycopg2.extras import RealDictCursor

from backend.src.auth.auth_router import get_current_user, get_db_connection

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/anomalies", tags=["anomalies"])


class FeedbackRequest(BaseModel):
    rating: str     # 'LIKE' or 'DISLIKE'


@router.get("")
def listAnomalies(
    atm_id: Optional[str] = Query(None),
    severity: Optional[str] = Query(None),
    is_active: Optional[int] = Query(None),
    anomaly_type: Optional[str] = Query(None),
    from_date: Optional[str] = Query(None),
    to_date: Optional[str] = Query(None),
    group_by: Optional[str] = Query(None),
    detection_source: Optional[str] = Query(None, description="Filter by detection source: CLASSIFIER, ZSCORE, SIGNAL_CORRELATOR"),
    is_starred: Optional[int] = Query(None, description="Filter by starred state: 1=starred, 0=unstarred"),
    sort_by: Optional[str] = Query(default="score", description="Sort by: score (default, criticality), detected_at (most recent), severity"),
    limit: int = Query(default=None, ge=0),
    offset: int = Query(default=0, ge=0),
    currentUser: dict = Depends(get_current_user),
    conn=Depends(get_db_connection)
):
    """Returns a paginated, filterable list of anomalies.
    Supports grouping modes: `atm`, `atm_anomaly`, `title_atm`.
    Default sort is by criticality score (score), not by most recent.
    Unknown anomalies (UNKNOWN type) are ranked lowest (score=0 + severity + age).
    """
    where_clauses = ["1=1"]
    params: list = []

    if atm_id:
        where_clauses.append("atm_id = %s")
        params.append(atm_id)
    if severity:
        where_clauses.append("severity = %s")
        params.append(severity.upper())
    if is_active is not None:
        where_clauses.append("is_active = %s")
        params.append(is_active)
    if anomaly_type:
        where_clauses.append("anomaly_type = %s")
        params.append(anomaly_type.upper())
    if from_date:
        where_clauses.append("detected_at >= %s")
        params.append(from_date)
    if to_date:
        where_clauses.append("detected_at <= %s")
        params.append(to_date)
    if detection_source:
        where_clauses.append("(explanation::jsonb)->>'source' = %s")
        params.append(detection_source.upper())
    if is_starred is not None:
        where_clauses.append("is_starred = %s")
        params.append(is_starred)

    where_sql = " AND ".join(where_clauses)

    if group_by:
        gb = group_by.lower()

        if gb in ("atm", "by_atm", "group_by_atm"):
            with conn.cursor() as cur:
                cur.execute(
                    f"SELECT COUNT(*) FROM (SELECT 1 FROM anomalies WHERE {where_sql} GROUP BY atm_id)",
                    params,
                )
                countRow = cur.fetchone()
            total = countRow[0] if countRow else 0

            query = f"""
                WITH groups AS (
                    SELECT
                        atm_id,
                        COUNT(*) AS count,
                        MAX(detected_at) AS latest,
                        MAX(CASE UPPER(severity)
                            WHEN 'CRITICAL' THEN 4 WHEN 'HIGH' THEN 3
                            WHEN 'MEDIUM' THEN 2 WHEN 'LOW' THEN 1 ELSE 0
                        END) AS max_severity_rank
                    FROM anomalies
                    WHERE {where_sql}
                    GROUP BY atm_id
                )
                SELECT
                    g.atm_id AS group_id,
                    g.atm_id,
                    g.count,
                    g.latest,
                    (
                        SELECT a2.id FROM anomalies a2
                        WHERE a2.atm_id = g.atm_id
                        ORDER BY CASE UPPER(a2.severity)
                            WHEN 'CRITICAL' THEN 4 WHEN 'HIGH' THEN 3
                            WHEN 'MEDIUM' THEN 2 WHEN 'LOW' THEN 1 ELSE 0
                        END DESC, a2.detected_at DESC
                        LIMIT 1
                    ) AS representative_id
                FROM groups g
                ORDER BY g.latest DESC
                LIMIT %s OFFSET %s
            """
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(query, params + [limit, offset])
                rows = cur.fetchall()
            return {"total": total, "limit": limit, "offset": offset, "data": [dict(r) for r in rows]}

        # group_by=atm_anomaly — one row per ATM + anomaly_type combo
        if gb in ("atm_anomaly", "atm-anomaly", "atm_anom"):
            with conn.cursor() as cur:
                cur.execute(
                    f"SELECT COUNT(*) FROM (SELECT 1 FROM anomalies WHERE {where_sql} GROUP BY atm_id, anomaly_type)",
                    params,
                )
                countRow = cur.fetchone()
            total = countRow[0] if countRow else 0

            query = f"""
                WITH groups AS (
                    SELECT
                        atm_id,
                        anomaly_type,
                        COUNT(*) AS count,
                        MAX(detected_at) AS latest_detected_at,
                        MAX(CASE UPPER(severity)
                            WHEN 'CRITICAL' THEN 4 WHEN 'HIGH' THEN 3
                            WHEN 'MEDIUM' THEN 2 WHEN 'LOW' THEN 1 ELSE 0
                        END) AS max_severity_rank
                    FROM anomalies
                    WHERE {where_sql}
                    GROUP BY atm_id, anomaly_type
                )
                SELECT
                    (g.atm_id || '__' || g.anomaly_type) AS group_id,
                    g.atm_id,
                    g.anomaly_type,
                    g.count,
                    g.latest_detected_at,
                    (
                        SELECT a2.id FROM anomalies a2
                        WHERE a2.atm_id = g.atm_id AND a2.anomaly_type = g.anomaly_type
                        ORDER BY CASE UPPER(a2.severity)
                            WHEN 'CRITICAL' THEN 4 WHEN 'HIGH' THEN 3
                            WHEN 'MEDIUM' THEN 2 WHEN 'LOW' THEN 1 ELSE 0
                        END DESC, a2.detected_at DESC
                        LIMIT 1
                    ) AS representative_id,
                    (
                        SELECT a3.title FROM anomalies a3
                        WHERE a3.atm_id = g.atm_id AND a3.anomaly_type = g.anomaly_type
                        ORDER BY CASE UPPER(a3.severity)
                            WHEN 'CRITICAL' THEN 4 WHEN 'HIGH' THEN 3
                            WHEN 'MEDIUM' THEN 2 WHEN 'LOW' THEN 1 ELSE 0
                        END DESC, a3.detected_at DESC
                        LIMIT 1
                    ) AS title,
                    (
                        SELECT a4.severity FROM anomalies a4
                        WHERE a4.atm_id = g.atm_id AND a4.anomaly_type = g.anomaly_type
                        ORDER BY CASE UPPER(a4.severity)
                            WHEN 'CRITICAL' THEN 4 WHEN 'HIGH' THEN 3
                            WHEN 'MEDIUM' THEN 2 WHEN 'LOW' THEN 1 ELSE 0
                        END DESC, a4.detected_at DESC
                        LIMIT 1
                    ) AS representative_severity,
                    (
                        SELECT a5.correlation_id FROM anomalies a5
                        WHERE a5.atm_id = g.atm_id AND a5.anomaly_type = g.anomaly_type
                        ORDER BY CASE UPPER(a5.severity)
                            WHEN 'CRITICAL' THEN 4 WHEN 'HIGH' THEN 3
                            WHEN 'MEDIUM' THEN 2 WHEN 'LOW' THEN 1 ELSE 0
                        END DESC, a5.detected_at DESC
                        LIMIT 1
                    ) AS correlation_id,
                    (
                        SELECT a6.is_starred FROM anomalies a6
                        WHERE a6.atm_id = g.atm_id AND a6.anomaly_type = g.anomaly_type
                        ORDER BY CASE UPPER(a6.severity)
                            WHEN 'CRITICAL' THEN 4 WHEN 'HIGH' THEN 3
                            WHEN 'MEDIUM' THEN 2 WHEN 'LOW' THEN 1 ELSE 0
                        END DESC, a6.detected_at DESC
                        LIMIT 1
                    ) AS is_starred
                FROM groups g
                ORDER BY g.latest_detected_at DESC
                LIMIT %s OFFSET %s
            """
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(query, params + [limit, offset])
                rows = cur.fetchall()
            return {"total": total, "limit": limit, "offset": offset, "data": [dict(r) for r in rows]}

        # group_by=title_atm — one row per title + ATM combo
        if gb in ("title_atm", "title-atm", "by_title_atm", "title"):
            with conn.cursor() as cur:
                cur.execute(
                    f"SELECT COUNT(*) FROM (SELECT 1 FROM anomalies WHERE {where_sql} GROUP BY title, atm_id)",
                    params,
                )
                countRow = cur.fetchone()
            total = countRow[0] if countRow else 0

            query = f"""
                WITH groups AS (
                    SELECT
                        title,
                        atm_id,
                        COUNT(*) AS count,
                        MAX(detected_at) AS latest
                    FROM anomalies
                    WHERE {where_sql}
                    GROUP BY title, atm_id
                )
                SELECT
                    (g.title || '::' || g.atm_id) AS group_id,
                    g.title,
                    g.atm_id,
                    g.count,
                    g.latest,
                    (
                        SELECT a2.id FROM anomalies a2
                        WHERE a2.atm_id = g.atm_id AND a2.title = g.title
                        ORDER BY CASE UPPER(a2.severity)
                            WHEN 'CRITICAL' THEN 4 WHEN 'HIGH' THEN 3
                            WHEN 'MEDIUM' THEN 2 WHEN 'LOW' THEN 1 ELSE 0
                        END DESC, a2.detected_at DESC
                        LIMIT 1
                    ) AS representative_id
                FROM groups g
                ORDER BY g.latest DESC
                LIMIT %s OFFSET %s
            """
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(query, params + [limit, offset])
                rows = cur.fetchall()
            return {"total": total, "limit": limit, "offset": offset, "data": [dict(r) for r in rows]}

    # Default — raw paginated anomalies, no grouping
    with conn.cursor() as cur:
        cur.execute(
            f"SELECT COUNT(*) FROM (SELECT 1 FROM anomalies WHERE {where_sql})", params
        )
        countRow = cur.fetchone()
    total = countRow[0] if countRow else 0

    # Build ORDER BY clause based on sort_by parameter
    # Score calculation: operation gravity (A1=7..A7=1, UNKNOWN=0) + severity (CRITICAL=3..) + age bonus
    if sort_by == "detected_at":
        order_clause = "detected_at DESC"
    elif sort_by == "severity":
        order_clause = """CASE UPPER(severity)
            WHEN 'CRITICAL' THEN 4 WHEN 'HIGH' THEN 3
            WHEN 'MAJOR' THEN 2 WHEN 'LOW' THEN 1 ELSE 0
        END DESC, detected_at DESC"""
    else:  # sort_by == "score" (default)
        # Score = operation_gravity + severity_rank + age_score
        # Age score: >48h=3, >24h=2, >6h=1, else=0
        order_clause = """(
            CASE anomaly_type
                WHEN 'A1' THEN 7 WHEN 'A4' THEN 6 WHEN 'A3' THEN 5
                WHEN 'A2' THEN 4 WHEN 'A6' THEN 3 WHEN 'A5' THEN 2
                WHEN 'A7' THEN 1 ELSE 0
            END +
            CASE UPPER(severity)
                WHEN 'CRITICAL' THEN 3 WHEN 'HIGH' THEN 2
                WHEN 'MAJOR' THEN 1 ELSE 0
            END +
            CASE
                WHEN detected_at < NOW() - INTERVAL '48 hours' THEN 3
                WHEN detected_at < NOW() - INTERVAL '24 hours' THEN 2
                WHEN detected_at < NOW() - INTERVAL '6 hours' THEN 1
                ELSE 0
            END
        ) DESC, detected_at DESC"""

    if limit is not None:
        query = f"SELECT * FROM anomalies WHERE {where_sql} ORDER BY {order_clause} LIMIT %s OFFSET %s"
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(query, params + [limit, offset])
            rows = cur.fetchall()
    else:
        query = f"SELECT * FROM anomalies WHERE {where_sql} ORDER BY {order_clause} OFFSET %s"
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(query, params + [offset])
            rows = cur.fetchall()
    return {"total": total, "limit": limit, "offset": offset, "data": [dict(r) for r in rows]}


@router.patch("/{anomalyId}/resolve")
def resolveAnomaly(
    anomalyId: int,
    currentUser: dict = Depends(get_current_user),
    conn=Depends(get_db_connection)
):
    """Marks an anomaly as resolved (is_active = 0) or unresolved."""
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("SELECT id, is_active FROM anomalies WHERE id = %s", (anomalyId,))
        row = cur.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Anomaly not found")

    new_active = 0 if row["is_active"] else 1
    with conn.cursor() as cur:
        cur.execute("UPDATE anomalies SET is_active = %s WHERE id = %s", (new_active, anomalyId))
    conn.commit()
    logger.info(f"Anomaly {anomalyId} active status toggled to {new_active} by '{currentUser['sub']}'")
    return {"id": anomalyId, "is_active": new_active, "message": "Anomaly status toggled"}


@router.patch("/{anomalyId}/star")
def toggleStar(
    anomalyId: int,
    currentUser: dict = Depends(get_current_user),
    conn=Depends(get_db_connection)
):
    """Toggles the starred state of an anomaly.
    Any logged-in user can star — no admin required.
    """
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("SELECT id, is_starred FROM anomalies WHERE id = %s", (anomalyId,))
        row = cur.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Anomaly not found")
    newStarred = 0 if row["is_starred"] else 1
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE anomalies SET is_starred = %s WHERE id = %s",
            (newStarred, anomalyId),
        )
    conn.commit()
    logger.info(
        f"Anomaly {anomalyId} starred={newStarred} by '{currentUser['sub']}'")
    return {"id": anomalyId, "is_starred": newStarred}


@router.patch("/{anomalyId}/feedback")
def setFeedback(
    anomalyId: int,
    body: FeedbackRequest,
    currentUser: dict = Depends(get_current_user),
    conn=Depends(get_db_connection),
):
    """Record feedback (LIKE=confirm, DISLIKE=false positive) on an anomaly.

    DISLIKE marks the anomaly as a false positive and increments the
    false_positive_count for this anomaly.
    """
    rating = body.rating.upper()
    if rating not in ("LIKE", "DISLIKE"):
        raise HTTPException(status_code=400, detail="Rating must be LIKE or DISLIKE")

    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            "SELECT id, anomaly_type, atm_id, false_positive_count FROM anomalies WHERE id = %s",
            (anomalyId,)
        )
        row = cur.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Anomaly not found")

    fp_inc = 1 if rating == "DISLIKE" else 0
    fp_count = (row["false_positive_count"] or 0) + fp_inc

    with conn.cursor() as cur:
        cur.execute(
            "UPDATE anomalies SET feedback_rating = %s, false_positive_count = %s WHERE id = %s",
            (rating, fp_count, anomalyId),
        )
    conn.commit()

    if rating == "DISLIKE":
        logger.info(
            "False positive reported for anomaly %s (type=%s, atm=%s). "
            "FP count for this (type, atm) pair incremented to %d",
            anomalyId, row["anomaly_type"], row["atm_id"], fp_count
        )

    return {
        "id": anomalyId,
        "feedback_rating": rating,
        "false_positive_count": fp_count,
    }
