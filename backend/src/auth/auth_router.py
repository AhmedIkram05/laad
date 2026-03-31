"""Authentication and RBAC router.

Endpoints:
    POST /auth/login          — username + password -> JWT
    GET  /auth/me             — returns current user's info
    POST /auth/register       — create a new user account
"""
from __future__ import annotations

import logging
import os
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
