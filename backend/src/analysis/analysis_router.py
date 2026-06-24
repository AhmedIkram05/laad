from __future__ import annotations
import logging
from fastapi import APIRouter, HTTPException, Query
from typing import Optional

from backend.src.analysis.analysis import main as run_analysis
from backend.src.analysis.metrics import (
    get_time_bucketed_anomalies,
    get_anomaly_summary,
)

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
        raise HTTPException(
            status_code=500, detail="Analysis service unavailable"
        ) from e


@router.get("/metrics")
def get_anomaly_metrics(
    hours: int = Query(24, ge=1, le=168),  # 1 hour to 7 days
    bucket_minutes: int = Query(60, ge=5, le=1440),  # 5 min to 24 hours
    anomaly_type: Optional[str] = Query(None),
    severity: Optional[str] = Query(None),
    is_active: Optional[int] = Query(None),
):
    """
    Returns time-bucketed anomaly counts for dashboard visualization.
    """
    try:
        time_series = get_time_bucketed_anomalies(
            hours=hours,
            bucket_minutes=bucket_minutes,
            anomaly_type=anomaly_type,
            severity=severity,
            is_active=is_active,
        )
        summary = get_anomaly_summary()
        return {
            "time_series": time_series,
            "summary": summary,
            "parameters": {
                "hours": hours,
                "bucket_minutes": bucket_minutes,
                "anomaly_type": anomaly_type,
                "severity": severity,
                "is_active": is_active,
            },
        }
    except Exception as e:
        logger.error("Metrics endpoint failed: %s", e, exc_info=True)
        raise HTTPException(
            status_code=500, detail="Metrics service unavailable"
        ) from e
