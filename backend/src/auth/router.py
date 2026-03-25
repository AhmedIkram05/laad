"""Authentication, RBAC and OTP router.

Endpoints:
    POST /auth/login          — username + password -> JWT
    GET  /auth/me             — returns current user's info
    POST /auth/otp/generate   — admin generates a shareable one-time token
    POST /auth/otp/redeem     — exchanges OTP token for a JWT session
"""
from __future__ import annotations

import logging
import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Generator

import bcrypt
import jwt
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from pydantic import BaseModel

from backend.database.connection import get_db

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
SECRET_KEY = os.environ.get("JWT_SECRET_KEY", "dev-secret-change-in-production!")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_HOURS = 8

router = APIRouter(prefix="/auth", tags=["auth"])
oauth2Scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


# ---------------------------------------------------------------------------
# DB connection dependency
# Guarantees conn.close() is always called, even if the endpoint throws.
# ---------------------------------------------------------------------------
def getDbConnection() -> Generator:
    conn = get_db()
    try:
        yield conn
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Token utilities
# ---------------------------------------------------------------------------
def createAccessToken(username: str, role: str) -> str:
    """Creates a signed JWT valid for ACCESS_TOKEN_EXPIRE_HOURS."""
    expire = datetime.now(timezone.utc) + timedelta(hours=ACCESS_TOKEN_EXPIRE_HOURS)
    payload = {"sub": username, "role": role, "exp": expire}
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


# ---------------------------------------------------------------------------
# Route dependency injectors
# ---------------------------------------------------------------------------
def getCurrentUser(token: str = Depends(oauth2Scheme)) -> dict:
    """Validates JWT. Returns {'sub': username, 'role': role}.
    Inject with Depends(getCurrentUser) on any route requiring login.
    """
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session expired, please log in again"
        )
    except jwt.PyJWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token"
        )


def requireAdmin(currentUser: dict = Depends(getCurrentUser)) -> dict:
    """Raises 403 if the current user is not an admin.
    Inject with Depends(requireAdmin) on any admin-only route.
    """
    if currentUser.get("role") != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required"
        )
    return currentUser


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------
class OtpGenerateRequest(BaseModel):
    role: str = "user"


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------
@router.post("/login")
def login(
    form: OAuth2PasswordRequestForm = Depends(),
    conn=Depends(getDbConnection)
):
    """Standard username/password login. Returns a JWT."""
    row = conn.execute(
        "SELECT password_hash, role FROM users WHERE username = ?",
        (form.username,)
    ).fetchone()

    if not row or not bcrypt.checkpw(form.password.encode(), row["password_hash"].encode()):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password"
        )

    token = createAccessToken(username=form.username, role=row["role"])
    logger.info(f"Login: '{form.username}' (role={row['role']})")
    return {"access_token": token, "token_type": "bearer", "role": row["role"]}


@router.get("/me")
def getMe(currentUser: dict = Depends(getCurrentUser)):
    """Returns the current user's username and role.
    Sarah calls this on page load to determine which UI elements to show.
    """
    return {"username": currentUser["sub"], "role": currentUser["role"]}


@router.post("/otp/generate")
def generateOtpToken(
    request: OtpGenerateRequest,
    currentUser: dict = Depends(requireAdmin),
    conn=Depends(getDbConnection)
):
    """Admin only. Generates a one-time access token valid for 24 hours.
    Returns a shareable link the admin pastes directly to the guest.
    """
    if request.role not in ("admin", "user"):
        raise HTTPException(status_code=400, detail="Role must be 'admin' or 'user'")

    token = uuid.uuid4().hex
    expiresAt = datetime.now(timezone.utc) + timedelta(hours=24)

    adminRow = conn.execute(
        "SELECT id FROM users WHERE username = ?",
        (currentUser["sub"],)
    ).fetchone()
    adminId = adminRow["id"] if adminRow else None

    conn.execute(
        """INSERT INTO otp_tokens (token, role, created_by, created_at, expires_at)
           VALUES (?, ?, ?, ?, ?)""",
        (
            token,
            request.role,
            adminId,
            datetime.now(timezone.utc).isoformat(),
            expiresAt.isoformat()
        )
    )
    conn.commit()

    link = f"http://localhost:5173/login?token={token}"
    logger.info(f"OTP generated by '{currentUser['sub']}' for role={request.role}")
    return {
        "token": token,
        "link": link,
        "role": request.role,
        "expires_at": expiresAt.isoformat()
    }


@router.post("/otp/redeem")
def redeemOtpToken(token: str, conn=Depends(getDbConnection)):
    """Exchanges a one-time token for a JWT. Invalidates the token immediately.
    Called by the frontend when it detects ?token= in the URL on the login page.
    """
    now = datetime.now(timezone.utc)
    row = conn.execute(
        "SELECT id, role, expires_at, used_at FROM otp_tokens WHERE token = ?",
        (token,)
    ).fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="Token not found")
    if row["used_at"]:
        raise HTTPException(status_code=410, detail="Token already used")
    if datetime.fromisoformat(row["expires_at"]).replace(tzinfo=timezone.utc) < now:
        raise HTTPException(status_code=410, detail="Token expired")

    # Invalidate immediately — one use only
    conn.execute(
        "UPDATE otp_tokens SET used_at = ? WHERE id = ?",
        (now.isoformat(), row["id"])
    )
    conn.commit()

    guestUsername = f"guest_{token[:8]}"
    jwtToken = createAccessToken(username=guestUsername, role=row["role"])
    logger.info(f"OTP redeemed, guest session created (role={row['role']})")
    return {"access_token": jwtToken, "token_type": "bearer", "role": row["role"]}
