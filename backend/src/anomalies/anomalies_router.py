"""Anomalies router.

Endpoints:
    GET   /anomalies                    — paginated, filterable anomaly list
    GET   /anomalies/{id}               — single anomaly detail
    PATCH /anomalies/{id}/resolve       — mark anomaly inactive (admin only)
    POST  /anomalies/{id}/feedback      — submit like/dislike rating
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from backend.src.auth.auth_router import get_current_user, get_db_connection, require_admin

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/anomalies", tags=["anomalies"])


class FeedbackRequest(BaseModel):
    rating: str     # 'LIKE' or 'DISLIKE'

# List anomalies
@router.get("")
def listAnomalies(
    atm_id: Optional[str] = Query(None),
    severity: Optional[str] = Query(None),
    is_active: Optional[int] = Query(None),
    anomaly_type: Optional[str] = Query(None),
    from_date: Optional[str] = Query(None),
    to_date: Optional[str] = Query(None),
    limit: int = Query(default=100, le=500),
    offset: int = Query(default=0, ge=0),
    currentUser: dict = Depends(get_current_user),
    conn=Depends(get_db_connection)
):
    """Returns a paginated, filterable list of anomalies.
    All logged-in users can access this endpoint.
    """
    query = "SELECT * FROM anomalies WHERE 1=1"
    params = []

    if atm_id:
        query += " AND atm_id = ?"
        params.append(atm_id)
    if severity:
        query += " AND severity = ?"
        params.append(severity.upper())
    if is_active is not None:
        query += " AND is_active = ?"
        params.append(is_active)
    if anomaly_type:
        query += " AND anomaly_type = ?"
        params.append(anomaly_type.upper())
    if from_date:
        query += " AND detected_at >= ?"
        params.append(from_date)
    if to_date:
        query += " AND detected_at <= ?"
        params.append(to_date)

    countRow = conn.execute(
        f"SELECT COUNT(*) FROM ({query})", params
    ).fetchone()
    total = countRow[0] if countRow else 0

    query += " ORDER BY detected_at DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])

    rows = conn.execute(query, params).fetchall()
    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "data": [dict(row) for row in rows]
    }


# Get single anomaly
@router.get("/{anomalyId}")
def getAnomaly(
    anomalyId: int,
    currentUser: dict = Depends(get_current_user),
    conn=Depends(get_db_connection)
):
    """Returns a single anomaly by ID."""
    row = conn.execute(
        "SELECT * FROM anomalies WHERE id = ?", (anomalyId,)
    ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Anomaly not found")
    return dict(row)


# Resolve anomaly
@router.patch("/{anomalyId}/resolve")
def resolveAnomaly(
    anomalyId: int,
    currentUser: dict = Depends(get_current_user),
    conn=Depends(get_db_connection)
):
    """Admin only. Marks an anomaly as resolved (is_active = 0)."""
    row = conn.execute(
        "SELECT id, is_active FROM anomalies WHERE id = ?", (anomalyId,)
    ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Anomaly not found")
    if not row["is_active"]:
        raise HTTPException(status_code=400, detail="Anomaly is already resolved")

    conn.execute(
        "UPDATE anomalies SET is_active = 0 WHERE id = ?", (anomalyId,)
    )
    conn.commit()
    logger.info(f"Anomaly {anomalyId} resolved by '{currentUser['sub']}'")
    return {"id": anomalyId, "is_active": 0, "message": "Anomaly resolved"}


# Submit feedback
@router.post("/{anomalyId}/feedback")
def submitFeedback(
    anomalyId: int,
    request: FeedbackRequest,
    currentUser: dict = Depends(get_current_user),
    conn=Depends(get_db_connection)
):
    """Submit like/dislike feedback on an anomaly.
    Overwrites any existing rating — one rating per anomaly.
    """
    if request.rating not in ("LIKE", "DISLIKE"):
        raise HTTPException(
            status_code=400,
            detail="Rating must be 'LIKE' or 'DISLIKE'"
        )
    row = conn.execute(
        "SELECT id FROM anomalies WHERE id = ?", (anomalyId,)
    ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Anomaly not found")

    conn.execute(
        "UPDATE anomalies SET feedback_rating = ? WHERE id = ?",
        (request.rating, anomalyId)
    )
    conn.commit()
    return {"id": anomalyId, "feedback_rating": request.rating}


# Toggle starred status
@router.patch("/{anomalyId}/star")
def toggleStar(
    anomalyId: int,
    currentUser: dict = Depends(get_current_user),
    conn=Depends(get_db_connection)
):
    """Toggles the starred state of an anomaly.
    Any logged-in user can star anomalies — no admin required.
    Returns the new starred state.
    """
    row = conn.execute(
        "SELECT id, is_starred FROM anomalies WHERE id = ?", (anomalyId,)
    ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Anomaly not found")

    newStarred = 0 if row["is_starred"] else 1
    conn.execute(
        "UPDATE anomalies SET is_starred = ? WHERE id = ?",
        (newStarred, anomalyId)
    )
    conn.commit()
    logger.info(f"Anomaly {anomalyId} starred={newStarred} by '{currentUser['sub']}'")
    return {"id": anomalyId, "is_starred": newStarred}