"""Events router.

Endpoints:
    GET /events  — paginated, filterable events via v_events_flat view
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, Query

from backend.src.auth.auth_router import get_current_user, get_db_connection

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/events", tags=["events"])


@router.get("")
def listEvents(
    atm_id: Optional[str] = Query(None),
    source: Optional[str] = Query(None),
    severity: Optional[str] = Query(None),
    correlation_id: Optional[str] = Query(None),
    from_date: Optional[str] = Query(None),
    to_date: Optional[str] = Query(None),
    limit: int = Query(default=100, le=500),
    offset: int = Query(default=0, ge=0),
    currentUser: dict = Depends(get_current_user),
    conn=Depends(get_db_connection)
):
    """Returns paginated events using the v_events_flat view.
    Extracts common JSON payload fields as first-class columns.
    """
    query = "SELECT * FROM v_events_flat WHERE 1=1"
    params = []

    if atm_id:
        query += " AND atm_id = ?"
        params.append(atm_id)
    if source:
        query += " AND source = ?"
        params.append(source.upper())
    if severity:
        query += " AND severity = ?"
        params.append(severity.upper())
    if correlation_id:
        query += " AND correlation_id = ?"
        params.append(correlation_id)
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