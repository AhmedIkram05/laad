"""Admin router — retention config and manual cleanup trigger."""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
import sqlite3

from backend.src.auth.auth_router import get_db_connection, require_admin
from backend.src.admin.cleanup import run_wipe

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["admin"])

ALLOWED_RETENTION_DAYS = [1, 7, 30, 60, 90, 365]


class RetentionUpdateRequest(BaseModel):
    days: int


class AdminCreateUserRequest(BaseModel):
    username: str
    password: str
    confirm_password: str
    role: str = "user"


@router.get("/retention", dependencies=[Depends(require_admin)])
def get_retention(conn=Depends(get_db_connection)):
    """Returns the current retention period."""
    row = conn.execute(
        "SELECT retention_days, updated_at FROM retention_config WHERE id = 1"
    ).fetchone()
    if not row:
        raise HTTPException(status_code=500, detail="Retention config not found")
    return {"retention_days": row["retention_days"], "updated_at": row["updated_at"]}


@router.put("/retention", dependencies=[Depends(require_admin)])
def update_retention(request: RetentionUpdateRequest, conn=Depends(get_db_connection)):
    """Admin only. Updates the data retention period.
    Allowed values: 1, 7, 30, 60, 90, 365 days.
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


@router.post("/cleanup/wipe", dependencies=[Depends(require_admin)])
def trigger_wipe():
    """Admin only. Permanently deletes all rows from cleanup tables and VACUUMs.

    This is a destructive operation. Only admin access is allowed.
    """
    return run_wipe()


@router.post("/users", dependencies=[Depends(require_admin)], status_code=201)
def admin_create_user(request: AdminCreateUserRequest, conn=Depends(get_db_connection), current_user: dict = Depends(require_admin)):
    """Admin-only endpoint to create persistent users (role may be 'admin' or 'user')."""
    # Ensure password confirmation matches
    if request.password != request.confirm_password:
        raise HTTPException(status_code=400, detail="passwords do not match")
    if request.role not in ("admin", "user"):
        raise HTTPException(status_code=400, detail="Role must be 'admin' or 'user'")

    try:
        import bcrypt
        password_hash = bcrypt.hashpw(request.password.encode(), bcrypt.gensalt()).decode()
    except Exception:
        raise HTTPException(status_code=500, detail="bcrypt unavailable")

    try:
        cur = conn.execute(
            "INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)",
            (request.username, password_hash, request.role),
        )
        conn.commit()
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=409, detail="username already exists")

    # Return created user info
    user_id = cur.lastrowid if cur is not None else None
    logger.info(f"Admin '{current_user.get('sub')}' created user '{request.username}' role={request.role}")
    return {"id": user_id, "username": request.username, "role": request.role}