"""Metrics router.

Endpoints:
    GET /metrics  — paginated, filterable metrics via v_metrics_flat view
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, Query

from backend.src.auth.auth_router import get_current_user, get_db_connection

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/metrics", tags=["metrics"])


@router.get("")
def listMetrics(
    entity_id: Optional[str] = Query(None),
    source: Optional[str] = Query(None),
    metric_name: Optional[str] = Query(None),
    from_date: Optional[str] = Query(None),
    to_date: Optional[str] = Query(None),
    limit: int = Query(default=100, le=500),
    offset: int = Query(default=0, ge=0),
    currentUser: dict = Depends(get_current_user),
    conn=Depends(get_db_connection)
):
    """Returns paginated metrics using the v_metrics_flat view."""
    query = "SELECT * FROM v_metrics_flat WHERE 1=1"
    params = []

    if entity_id:
        query += " AND atm_id = ?"
        params.append(entity_id)
    if source:
        query += " AND source = ?"
        params.append(source.upper())
    if metric_name:
        query += " AND metric_name = ?"
        params.append(metric_name)
    if from_date:
        query += " AND timestamp >= ?"
        params.append(from_date)
    if to_date:
        query += " AND timestamp <= ?"
        params.append(to_date)

    countRow = conn.execute(
        f"SELECT COUNT(*) FROM ({query})", params
    ).fetchone()
    total = countRow[0] if countRow else 0

    query += " ORDER BY timestamp DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])

    rows = conn.execute(query, params).fetchall()
    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "data": [dict(row) for row in rows]
    }