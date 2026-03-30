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
import sqlite3

from backend.src.database.connection import get_db

logger = logging.getLogger(__name__)

# Config
SECRET_KEY = os.environ.get("JWT_SECRET_KEY", "dev-secret-change-in-production!")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_HOURS = 8

router = APIRouter(prefix="/auth", tags=["auth"])
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


# DB connection dependency
# Guarantees conn.close() is always called, even if the endpoint throws.
def get_db_connection() -> Generator:
    conn = get_db()
    try:
        yield conn
    finally:
        conn.close()


# Token utilities
def create_access_token(username: str, role: str) -> str:
    """Creates a signed JWT valid for ACCESS_TOKEN_EXPIRE_HOURS."""
    expire = datetime.now(timezone.utc) + timedelta(hours=ACCESS_TOKEN_EXPIRE_HOURS)
    payload = {"sub": username, "role": role, "exp": expire}
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


# Route dependency injectors
def get_current_user(token: str = Depends(oauth2_scheme)) -> dict:
    """Validates JWT. Returns {'sub': username, 'role': role}.
    Inject with Depends(get_current_user) on any route requiring login.
    """
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session expired, please log in again",
        )
    except jwt.PyJWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
        )


def require_admin(current_user: dict = Depends(get_current_user)) -> dict:
    """Raises 403 if the current user is not an admin.
    Inject with Depends(require_admin) on any admin-only route.
    """
    if current_user.get("role") != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )
    return current_user


# Request models
class OtpGenerateRequest(BaseModel):
    role: str = "user"


class RegisterRequest(BaseModel):
    username: str
    password: str


# Endpoints
@router.post("/login")
def login(
    form: OAuth2PasswordRequestForm = Depends(),
    conn=Depends(get_db_connection),
):
    """Standard username/password login. Returns a JWT."""
    row = conn.execute(
        "SELECT password_hash, role FROM users WHERE username = ?",
        (form.username,),
    ).fetchone()

    if not row or not bcrypt.checkpw(form.password.encode(), row["password_hash"].encode()):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
        )

    token = create_access_token(username=form.username, role=row["role"])
    logger.info(f"Login: '{form.username}' (role={row['role']})")
    return {"access_token": token, "token_type": "bearer", "role": row["role"]}


@router.get("/me")
def get_me(current_user: dict = Depends(get_current_user)):
    """Returns the current user's username and role.
    Sarah calls this on page load to determine which UI elements to show.
    """
    return {"username": current_user["sub"], "role": current_user["role"]}


@router.post("/otp/generate")
def generate_otp_token(
    request: OtpGenerateRequest,
    current_user: dict = Depends(require_admin),
    conn=Depends(get_db_connection),
):
    """Admin only. Generates a one-time access token valid for 24 hours.
    Returns a shareable link the admin pastes directly to the guest.
    """
    if request.role not in ("admin", "user"):
        raise HTTPException(status_code=400, detail="Role must be 'admin' or 'user'")

    token = uuid.uuid4().hex
    expires_at = datetime.now(timezone.utc) + timedelta(hours=24)

    admin_row = conn.execute(
        "SELECT id FROM users WHERE username = ?",
        (current_user["sub"],),
    ).fetchone()
    admin_id = admin_row["id"] if admin_row else None

    conn.execute(
        """INSERT INTO otp_tokens (token, role, created_by, created_at, expires_at)
           VALUES (?, ?, ?, ?, ?)""",
        (
            token,
            request.role,
            admin_id,
            datetime.now(timezone.utc).isoformat(),
            expires_at.isoformat(),
        ),
    )
    conn.commit()

    link = f"http://localhost:5173/login?token={token}"
    logger.info(f"OTP generated by '{current_user['sub']}' for role={request.role}")
    return {
        "token": token,
        "link": link,
        "role": request.role,
        "expires_at": expires_at.isoformat(),
    }


@router.post("/otp/redeem")
def redeem_otp_token(token: str, conn=Depends(get_db_connection)):
    """Exchanges a one-time token for a JWT. Invalidates the token immediately.
    Called by the frontend when it detects ?token= in the URL on the login page.
    """
    now = datetime.now(timezone.utc)
    row = conn.execute(
        "SELECT id, role, expires_at, used_at FROM otp_tokens WHERE token = ?",
        (token,),
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
        (now.isoformat(), row["id"]),
    )
    conn.commit()

    guest_username = f"guest_{token[:8]}"
    jwt_token = create_access_token(username=guest_username, role=row["role"])
    logger.info(f"OTP redeemed, guest session created (role={row['role']})")
    return {"access_token": jwt_token, "token_type": "bearer", "role": row["role"]}



@router.post("/register", status_code=201)
def register(request: RegisterRequest, conn=Depends(get_db_connection)):
    """Create a new user account.

    Minimal fields required: `username`, `password`.
    Does not auto-login; returns HTTP 201 on success.
    """
    # Basic validation
    if not request.username or not request.password:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="username and password are required")

    if len(request.password) < 6:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="password must be at least 6 characters")

    # Hash the password and insert the user
    password_hash = bcrypt.hashpw(request.password.encode(), bcrypt.gensalt()).decode()
    try:
        cur = conn.execute(
            "INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)",
            (request.username, password_hash, "user"),
        )
        conn.commit()
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="username already exists")

    user_id = cur.lastrowid if cur is not None else None
    logger.info(f"New user created: '{request.username}' (id={user_id})")
    return {"message": "Account created successfully", "username": request.username, "id": user_id}
