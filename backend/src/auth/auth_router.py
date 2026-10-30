"""Authentication and RBAC router.

Endpoints:
    POST /auth/login          — username + password -> JWT
    GET  /auth/me             — returns current user's info
    POST /auth/register       — create a new user account
    POST /auth/logout         — blacklist current JWT (requires auth)
"""

from __future__ import annotations

import hashlib
import logging
import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Generator

import bcrypt
import jwt
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from pydantic import BaseModel

import psycopg2
from psycopg2.extras import RealDictCursor

from backend.src.cache import get_redis_client
from backend.src.database.connection import get_conn, release_conn

logger = logging.getLogger(__name__)

# Config
MIN_SECRET_KEY_BYTES = 32

# JWT_SECRET_KEY must be set in production via AWS Secrets Manager


def _load_secret_key() -> str:
    """Returns an HS256-compatible JWT secret key.

    JWT_SECRET_KEY must be set in production via AWS Secrets Manager.
    Raises RuntimeError at module import time if not configured or shorter
    than MIN_SECRET_KEY_BYTES — padding a short secret up would silently
    weaken entropy, so fail fast instead.
    """
    secret_key = os.environ.get("JWT_SECRET_KEY")
    if secret_key is None:
        raise RuntimeError(
            "JWT_SECRET_KEY environment variable is required. "
            "Set it in production via AWS Secrets Manager."
        )
    secret_key_bytes = len(secret_key.encode("utf-8"))
    if secret_key_bytes < MIN_SECRET_KEY_BYTES:
        raise RuntimeError(
            f"JWT_SECRET_KEY must be at least {MIN_SECRET_KEY_BYTES} bytes "
            f"(got {secret_key_bytes}). Set a longer secret in production "
            "via AWS Secrets Manager."
        )
    return secret_key


SECRET_KEY = _load_secret_key()
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_HOURS = 8

router = APIRouter(prefix="/auth", tags=["auth"])
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")
_optional_oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login", auto_error=False)

AUTH_COOKIE_NAME = "access_token"
COOKIE_SECURE = os.getenv("COOKIE_SECURE", "false").lower() == "true"

if os.getenv("LAAD_ENV") == "production" and not COOKIE_SECURE:
    logger.warning(
        "COOKIE_SECURE=false with LAAD_ENV=production — auth cookies will be "
        "sent over plaintext HTTP; set COOKIE_SECURE=true behind TLS"
    )

# Burn-hash for uniform login timing: when the username is unknown we still
# run a bcrypt comparison against this throwaway hash so response latency
# does not reveal whether the account exists. Derived from random bytes at
# import time — it is not a real password and never matches user input.
_DUMMY_HASH = bcrypt.hashpw(secrets.token_bytes(32), bcrypt.gensalt())


def _set_auth_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        AUTH_COOKIE_NAME,
        token,
        max_age=ACCESS_TOKEN_EXPIRE_HOURS * 3600,
        httponly=True,
        samesite="lax",
        secure=COOKIE_SECURE,
        path="/",
    )


# DB connection dependency
# Guarantees conn.close() is always called, even if the endpoint throws.
def get_db_connection() -> Generator:
    conn = get_conn()
    try:
        yield conn
    finally:
        release_conn(conn)


# Token utilities
def create_access_token(username: str, role: str) -> str:
    """Creates a signed JWT valid for ACCESS_TOKEN_EXPIRE_HOURS."""
    expire = datetime.now(timezone.utc) + timedelta(hours=ACCESS_TOKEN_EXPIRE_HOURS)
    payload = {"sub": username, "role": role, "exp": expire}
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def _get_token_hash(token: str) -> str:
    """Generate a SHA256 hash of the JWT for blacklist storage."""
    return hashlib.sha256(token.encode()).hexdigest()


def _is_token_blacklisted(token: str) -> bool:
    """Check if a token is in the Redis blacklist.

    Fail-open on Redis failure is a deliberate availability trade-off: during
    an outage, revoked tokens remain valid until Redis recovers. The short
    token TTL (ACCESS_TOKEN_EXPIRE_HOURS) bounds the exposure window.
    Failures are logged at ERROR (auth_blocklist_fail_open) so they are
    alertable rather than silent.
    """
    client = get_redis_client()
    if client is None:
        logger.error("auth_blocklist_fail_open reason=%s", "redis_unavailable")
        return False
    try:
        token_hash = _get_token_hash(token)
        return bool(client.get(f"blacklist:{token_hash}"))
    except Exception as exc:
        logger.error("auth_blocklist_fail_open reason=%s", exc)
        return False


def _blacklist_token(token: str, expires_at: datetime) -> None:
    """Add a token to the Redis blacklist with TTL = remaining token expiry."""
    client = get_redis_client()
    if client is None:
        return
    token_hash = _get_token_hash(token)
    now = datetime.now(timezone.utc)
    ttl_seconds = max(int((expires_at - now).total_seconds()), 60)
    client.set(f"blacklist:{token_hash}", "1", ex=ttl_seconds)
    logger.info(f"Token blacklisted (TTL={ttl_seconds}s)")


# Route dependency injectors
def get_current_user(
    token: str | None = Depends(_optional_oauth2_scheme),
    request: Request = None,  # type: ignore[assignment]
) -> dict:
    """Validates JWT and checks blacklist. Returns {'sub': username, 'role': role}.
    Inject with Depends(get_current_user) on any route requiring login.
    Accepts Authorization header first, httpOnly cookie as fallback.
    Token-first signature keeps direct unit-test calls (get_current_user(token))
    working; FastAPI injects both params by type/Depends regardless of order.
    """
    if not isinstance(token, str):
        token = None
    if token is None and request is not None:
        token = request.cookies.get(AUTH_COOKIE_NAME)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
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

    if _is_token_blacklisted(token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has been revoked, please log in again",
        )

    return payload


def require_admin(
    current_user: dict = Depends(get_current_user),
    conn=Depends(get_db_connection),
) -> dict:
    """Raises 403 if the current user is not an admin.
    Inject with Depends(require_admin) on any admin-only route.

    The JWT role claim is a login-time snapshot (valid up to
    ACCESS_TOKEN_EXPIRE_HOURS), so it is only a fast path: before granting
    access we re-read the user's CURRENT role from the DB, which costs one
    indexed primary-key lookup per admin request. Non-admins are rejected
    by the JWT check before any DB round-trip.
    """
    if current_user.get("role") != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )
    with conn.cursor() as cur:
        cur.execute(
            "SELECT role FROM users WHERE username = %s", (current_user["sub"],)
        )
        row = cur.fetchone()
    if not row or row[0] != "admin":
        # User deleted or demoted since login — the stale JWT no longer
        # grants admin access.
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
    response: Response,
    form: OAuth2PasswordRequestForm = Depends(),
    conn=Depends(get_db_connection),
):
    """Standard username/password login. Sets httpOnly cookie + returns a JWT
    (token in body kept for backwards compat with localStorage clients)."""
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            "SELECT password_hash, role FROM users WHERE username = %s",
            (form.username,),
        )
        row = cur.fetchone()

    if not row:
        # Uniform timing for unknown usernames: burn a bcrypt comparison
        # against the throwaway hash so latency matches the wrong-password
        # path and does not leak account existence.
        bcrypt.checkpw(form.password.encode(), _DUMMY_HASH)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
        )

    if not bcrypt.checkpw(form.password.encode(), row["password_hash"].encode()):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
        )

    token = create_access_token(username=form.username, role=row["role"])
    _set_auth_cookie(response, token)
    logger.info(f"Login: '{form.username}' (role={row['role']})")
    return {"access_token": token, "token_type": "bearer", "role": row["role"]}


@router.get("/me")
def get_me(current_user: dict = Depends(get_current_user)):
    """Returns the current user's username and role.
    Sarah calls this on page load to determine which UI elements to show.
    """
    return {"username": current_user["sub"], "role": current_user["role"]}


@router.post("/register", status_code=201)
def register(
    request: RegisterRequest,
    conn=Depends(get_db_connection),
    token: str | None = Depends(_optional_oauth2_scheme),
    http_request: Request = None,  # type: ignore[assignment]
):
    """Create a new user account.

    Minimal fields required: `username`, `password`.
    Does not auto-login; returns HTTP 201 on success.

    Requires an admin session by default. Set ALLOW_OPEN_REGISTRATION=true
    (or "1") in the environment to restore open self-service signup. The
    initial admin account is seeded at startup by init_db()
    (seed_default_admin), so operators can always bootstrap.
    """
    if os.getenv("ALLOW_OPEN_REGISTRATION", "false").lower() not in ("true", "1"):
        current_user = get_current_user(token=token, request=http_request)
        require_admin(current_user, conn)
    # Basic validation
    if not request.username or not request.password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="username and password are required",
        )

    if len(request.password) < 6:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="password must be at least 6 characters",
        )

    # Hash the password and insert the user
    password_hash = bcrypt.hashpw(request.password.encode(), bcrypt.gensalt()).decode()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO users (username, password_hash, role) VALUES (%s, %s, %s) RETURNING id",
                (request.username, password_hash, "user"),
            )
            user_id = cur.fetchone()[0]
        conn.commit()
    except psycopg2.IntegrityError:
        conn.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="username already exists"
        )
    logger.info(f"New user created: '{request.username}' (id={user_id})")
    return {
        "message": "Account created successfully",
        "username": request.username,
        "id": user_id,
    }


@router.post("/logout")
def logout(
    response: Response,
    token: str | None = Depends(_optional_oauth2_scheme),
    request: Request = None,  # type: ignore[assignment]
):
    """Revoke the current JWT by adding it to the Redis blacklist.

    The token is stored with TTL = remaining token expiry time.
    If Redis is unavailable, the endpoint returns success but logs a warning.
    """
    if not isinstance(token, str):
        token = None
    if token is None and request is not None:
        token = request.cookies.get(AUTH_COOKIE_NAME)
    response.delete_cookie(AUTH_COOKIE_NAME, path="/")
    if not token:
        return {"message": "Successfully logged out"}
    try:
        payload = jwt.decode(
            token, SECRET_KEY, algorithms=[ALGORITHM], options={"verify_exp": False}
        )
        expires_at = datetime.fromtimestamp(payload["exp"], tz=timezone.utc)
        _blacklist_token(token, expires_at)
        username = payload.get("sub", "unknown")
        logger.info(f"Logout: '{username}' — token blacklisted")
        return {"message": "Successfully logged out"}
    except jwt.PyJWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
        )
