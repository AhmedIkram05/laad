"""FastAPI web server entry point.

Run with:
    uvicorn backend.src.api.server:app --reload --port 8000
"""

from __future__ import annotations

import json
import logging
import os
import time
from contextlib import asynccontextmanager

from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse

from backend.src.admin.cleanup import run_cleanup
from backend.src.admin.admin_router import router as adminRouter
from backend.src.anomalies.anomalies_router import router as anomaliesRouter
from backend.src.auth.auth_router import router as authRouter
from backend.src.analysis.analysis_router import router as analysisRouter
from backend.src.analytics.analytics_router import router as analyticsRouter
from backend.src.rag.router import router as ragRouter
from backend.src.database.connection import get_conn, release_conn
from backend.src.database.init_db import init_db
from backend.src.anomaly_detection.ml.train import ARTIFACT_DIR
from backend.src.observability.tracing import instrument_fastapi, setup_tracing

setup_tracing("atm-backend")

logger = logging.getLogger(__name__)

scheduler = BackgroundScheduler()

_db_initialized = False


def _ensure_db_initialized() -> None:
    """Ensure database schema and seed data exist. Called on startup."""
    global _db_initialized
    if _db_initialized:
        return

    max_retries = 3
    for attempt in range(1, max_retries + 1):
        try:
            init_db()
            _db_initialized = True
            logger.info("Database initialised and seeded successfully")
            return
        except Exception as e:
            logger.error(
                "Database initialisation failed (attempt %d/%d): %s",
                attempt,
                max_retries,
                e,
            )
            if attempt < max_retries:
                time.sleep(2)
            else:
                raise


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manages scheduler startup and shutdown."""
    logger.info("Starting up — initialising database")
    _ensure_db_initialized()

    laad_env = os.getenv("LAAD_ENV", "")
    if laad_env == "production":
        logger.info("LAAD_ENV=production — skipping startup model check and retrain")
    else:
        _check_and_retrain_on_startup()

    scheduler.add_job(
        run_cleanup, "interval", hours=1, id="cleanup", misfire_grace_time=60
    )
    scheduler.start()
    logger.info("Schedulers started: cleanup (1h)")
    yield
    scheduler.shutdown()
    logger.info("Schedulers stopped")


def _check_and_retrain_on_startup() -> None:
    """Check if models exist on startup and train if absent or corrupted."""
    model_file = ARTIFACT_DIR / "xgb_classifier.joblib"
    if not model_file.exists():
        logger.info("No model artifacts found — training on startup")
        _do_retrain()
        return

    # Try to load models to see if they're valid (handles scikit-learn version skew)
    try:
        import joblib

        from backend.src.anomaly_detection.ml.feature_engineering import FEATURE_COUNT

        joblib.load(model_file)
        joblib.load(ARTIFACT_DIR / "isolation_forest.joblib")
        joblib.load(ARTIFACT_DIR / "label_encoder.joblib")
        scaler = joblib.load(ARTIFACT_DIR / "scaler.joblib")
        n_actual = getattr(scaler, "n_features_in_", FEATURE_COUNT)
        if n_actual != FEATURE_COUNT:
            raise ValueError(
                f"stale artifacts: scaler expects {n_actual} features, "
                f"code has {FEATURE_COUNT}"
            )
        logger.info("Model artifacts are valid — using existing models")
        return
    except Exception as e:
        logger.warning(
            "Model artifacts exist but are corrupted or incompatible: %s — retraining",
            e,
        )

    logger.info("No valid model artifacts found — training on startup")
    _do_retrain()


def _do_retrain() -> None:
    """Run the training pipeline.

    Calls the train module's entry point directly. The previous
    ``importlib.reload(train)`` re-read module-level constants that do not
    change between reloads (the module is imported at startup and its only
    module-level paths are derived from ``__file__``), while re-executing the
    module reset unrelated state as a side effect.
    """
    try:
        from backend.src.anomaly_detection.ml.train import train as run_train

        run_train()
        logger.info("Startup retrain complete")
    except Exception as exc:
        logger.error("Startup retrain failed: %s", exc, exc_info=True)


app = FastAPI(title="ATM Log Aggregation Platform", lifespan=lifespan)

instrument_fastapi(app)


class HealthExemptTrustedHostMiddleware(TrustedHostMiddleware):
    """TrustedHostMiddleware that skips validation for the health endpoint.

    The ALB health check sends the target's private IP as the Host header, so
    strict validation would mark the target permanently unhealthy. The current
    /health payload is static and host-independent, so exempting it is safe.
    """

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http" and scope["path"] == "/health":
            await self.app(scope, receive, send)
            return
        await super().__call__(scope, receive, send)


# Host header validation. Defaults keep local dev and the TestClient working;
# production must set ALLOWED_HOSTS to the real API hostname(s).
app.add_middleware(
    HealthExemptTrustedHostMiddleware,
    allowed_hosts=os.getenv("ALLOWED_HOSTS", "localhost,127.0.0.1,testserver").split(
        ","
    ),
    www_redirect=False,
)

# Reject oversized request bodies early. No endpoint accepts file uploads, so
# 1 MiB is generous for this JSON API. Content-Length is checked as a cheap
# fast path; the body is also counted as it streams through the wrapped ASGI
# receive callable, so a chunked body cannot bypass the cap by omitting
# Content-Length.
MAX_REQUEST_BODY_BYTES = int(os.getenv("MAX_REQUEST_BODY_BYTES", str(1024 * 1024)))


async def _send_json_response(send, status_code: int, content: dict) -> None:
    body = json.dumps(content).encode()
    await send(
        {
            "type": "http.response.start",
            "status": status_code,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(body)).encode()),
            ],
        }
    )
    await send({"type": "http.response.body", "body": body})


class LimitRequestBodyMiddleware:
    """Reject request bodies larger than MAX_REQUEST_BODY_BYTES.

    Content-Length is a cheap fast path. When it is absent (chunked bodies),
    the ASGI ``receive`` callable is wrapped to count bytes as they arrive and
    the request is rejected with 413 as soon as the cap is exceeded, without
    buffering the body. The body is passed through unchanged while under the
    cap; once exceeded, the downstream response is discarded and replaced by
    the 413 (FastAPI otherwise converts a mid-body abort into a 400).
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        max_bytes = MAX_REQUEST_BODY_BYTES
        content_length = None
        for key, value in scope["headers"]:
            if key == b"content-length":
                content_length = value
                break

        if content_length is not None:
            try:
                too_large = int(content_length) > max_bytes
            except ValueError:
                await _send_json_response(
                    send, 400, {"detail": "Invalid Content-Length header"}
                )
                return
            if too_large:
                await _send_json_response(
                    send, 413, {"detail": "Request body too large"}
                )
                return
            # Content-Length within the cap: stream the body straight through.
            await self.app(scope, receive, send)
            return

        received = 0
        exceeded = False
        response_started = False

        async def limited_receive():
            nonlocal received, exceeded
            if exceeded:
                # Stop feeding the body; the response is overridden below.
                return {"type": "http.request", "body": b"", "more_body": False}
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > max_bytes:
                    exceeded = True
                    return {"type": "http.request", "body": b"", "more_body": False}
            return message

        async def limited_send(message):
            nonlocal response_started
            if exceeded:
                if not response_started:
                    response_started = True
                    await _send_json_response(
                        send, 413, {"detail": "Request body too large"}
                    )
                return
            if message["type"] == "http.response.start":
                response_started = True
            await send(message)

        await self.app(scope, limited_receive, limited_send)


app.add_middleware(LimitRequestBodyMiddleware)


# CORS registered last so it wraps the middlewares above and its headers are
# present on the 400/413 error responses too.
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ORIGINS", "http://localhost:5173").split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health_check() -> dict:
    """Liveness probe for container orchestration."""
    return {"status": "ok"}


@app.get("/health/ready")
def readiness_check() -> dict:
    """Readiness probe — checks DB connectivity."""
    try:
        conn = get_conn()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
            return {"status": "ready", "database": "connected"}
        finally:
            release_conn(conn)
    except Exception as e:
        logger.warning("Readiness check failed: %s", e)
        raise HTTPException(status_code=503, detail="Database not ready") from e


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Catches unhandled exceptions and returns clean JSON."""
    logger.error("Unhandled exception on %s: %s", request.url, exc, exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": "An internal server error occurred"},
    )


# Routers
app.include_router(authRouter)
app.include_router(adminRouter)
app.include_router(anomaliesRouter)
app.include_router(analysisRouter)
app.include_router(analyticsRouter)
app.include_router(ragRouter)
