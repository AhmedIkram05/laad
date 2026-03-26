
"""ATMs router.

Endpoints:
    GET /atms       — all ATMs with derived health status
    GET /atms/{id}  — single ATM with active anomaly summary
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException

from backend.src.auth.auth_router import get_current_user, get_db_connection

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/atms", tags=["atms"])


@router.get("")
def listAtms(
    currentUser: dict = Depends(get_current_user),
    conn=Depends(get_db_connection)
):
    """Returns all ATMs with static fields and a derived health status.

    Status derived from active anomalies:
      CRITICAL — any active CRITICAL anomaly exists
      WARNING  — any active HIGH anomaly exists (but no CRITICAL)
      OK       — no active anomalies
    """
    rows = conn.execute("""
        SELECT
            a.atm_id,
            a.os_version,
            a.location_code,
            COUNT(an.id) AS active_anomaly_count,
            CASE
                WHEN MAX(CASE an.severity
                         WHEN 'CRITICAL' THEN 2
                         WHEN 'HIGH'     THEN 1
                         ELSE 0 END) = 2 THEN 'CRITICAL'
                WHEN MAX(CASE an.severity
                         WHEN 'CRITICAL' THEN 2
                         WHEN 'HIGH'     THEN 1
                         ELSE 0 END) = 1 THEN 'WARNING'
                ELSE 'OK'
            END AS status
        FROM atms a
        LEFT JOIN anomalies an
            ON a.atm_id = an.atm_id AND an.is_active = 1
        GROUP BY a.atm_id
        ORDER BY a.atm_id
    """).fetchall()

    return {"data": [dict(row) for row in rows]}


@router.get("/{atmId}")
def getAtm(
    atmId: str,
    currentUser: dict = Depends(get_current_user),
    conn=Depends(get_db_connection)
):
    """Returns a single ATM's static fields, derived status,
    and its currently active anomalies.
    """
    atmRow = conn.execute(
        "SELECT * FROM atms WHERE atm_id = ?", (atmId,)
    ).fetchone()
    if not atmRow:
        raise HTTPException(status_code=404, detail="ATM not found")

    activeAnomalies = conn.execute("""
        SELECT id, anomaly_type, severity, title, detected_at
        FROM anomalies
        WHERE atm_id = ? AND is_active = 1
        ORDER BY detected_at DESC
    """, (atmId,)).fetchall()

    severities = [row["severity"] for row in activeAnomalies]
    if "CRITICAL" in severities:
        status = "CRITICAL"
    elif "HIGH" in severities:
        status = "WARNING"
    else:
        status = "OK"

    return {
        **dict(atmRow),
        "status": status,
        "active_anomalies": [dict(row) for row in activeAnomalies]
    }