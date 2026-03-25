"""Admin router — retention config and manual cleanup trigger."""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from backend.src.auth.auth_router import getDbConnection, requireAdmin
from backend.src.admin.cleanup import runCleanup

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["admin"])

ALLOWED_RETENTION_DAYS = [7, 30, 60, 90, 365]


class RetentionUpdateRequest(BaseModel):
    days: int


@router.get("/retention", dependencies=[Depends(requireAdmin)])
def getRetention(conn=Depends(getDbConnection)):
    """Returns the current retention period."""
    row = conn.execute(
        "SELECT retention_days, updated_at FROM retention_config WHERE id = 1"
    ).fetchone()
    if not row:
        raise HTTPException(status_code=500, detail="Retention config not found")
    return {"retention_days": row["retention_days"], "updated_at": row["updated_at"]}


@router.put("/retention", dependencies=[Depends(requireAdmin)])
def updateRetention(request: RetentionUpdateRequest, conn=Depends(getDbConnection)):
    """Admin only. Updates the data retention period.
    Allowed values: 7, 30, 60, 90, 365 days.
    """
    if request.days not in ALLOWED_RETENTION_DAYS:
        raise HTTPException(
            status_code=400,
            detail=f"Allowed values: {ALLOWED_RETENTION_DAYS}"
        )
    conn.execute(
        "UPDATE retention_config SET retention_days = ?, updated_at = ? WHERE id = 1",
        (request.days, datetime.now(timezone.utc).isoformat())
    )
    conn.commit()
    logger.info(f"Retention period updated to {request.days} days")
    return {"retention_days": request.days, "message": "Retention period updated"}


@router.post("/cleanup/run", dependencies=[Depends(requireAdmin)])
def triggerCleanup():
    """Admin only. Manually triggers the cleanup job immediately."""
    return runCleanup()