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
    This would return the anomaly to frontend in the rank order which i mentioned(rank is fully by the anomalie not atm's)
    Also it contains all anomalie not just a2, it would give you the detailed analysis(recommended fix, operatoion impact, root cause)
    """
    try:
        data = run_analysis()
        return {
            "data": data
        }
    except Exception as e:
        logger.error(f"Analysis endpoint failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Analysis failed: {str(e)}")