from __future__ import annotations

import logging
from fastapi import APIRouter, Depends, HTTPException

from backend.src.auth.auth_router import get_current_user
from backend.src.analysis.analysis import main as run_analysis

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/analysis", tags=["analysis"])


@router.get("/detailed")
def get_detailed_analysis():
    """
    Returns anomalies ranked by weighted criticality score with root cause,
    operational impact, and recommended remediation action.
    """
    try:
        data = run_analysis()
        return {"data": data or []}
    except Exception as e:
        logger.error("Analysis endpoint failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Analysis service unavailable") from e