"""FastAPI web server entry point.

Run with:
    uvicorn backend.src.api.server:app --reload --port 8000
"""
from __future__ import annotations

import logging
import time
from contextlib import asynccontextmanager

from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from backend.src.admin.cleanup import run_cleanup
from backend.src.admin.admin_router import router as adminRouter
from backend.src.anomalies.anomalies_router import router as anomaliesRouter
from backend.src.auth.auth_router import router as authRouter
from backend.src.analysis.analysis_router import router as analysisRouter
from backend.src.analytics.analytics_router import router as analyticsRouter
from backend.src.anomaly_detection.ml.ml_detector import MLAnomalyDetector
from backend.src.database.connection import get_conn, release_conn
from backend.src.database.init_db import init_db
from backend.src.anomaly_detection.ml.train import ARTIFACT_DIR

logger = logging.getLogger(__name__)

scheduler = BackgroundScheduler()

_ml_detector: MLAnomalyDetector | None = None
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
            logger.error("Database initialisation failed (attempt %d/%d): %s", attempt, max_retries, e)
            if attempt < max_retries:
                time.sleep(2)
            else:
                raise


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manages scheduler startup and shutdown."""
    logger.info("Starting up — initialising database")
    _ensure_db_initialized()
    _check_and_retrain_on_startup()

    scheduler.add_job(run_cleanup, "interval", hours=1, id="cleanup", misfire_grace_time=60)
    scheduler.add_job(_run_ml_detection, "interval", seconds=30, id="ml_detector", misfire_grace_time=60)
    scheduler.add_job(_auto_retrain, "interval", hours=1, id="auto_retrain", misfire_grace_time=300)
    scheduler.start()
    logger.info("Schedulers started: cleanup (1h), ml_detector (30s), auto_retrain (1h)")
    yield
    scheduler.shutdown()
    logger.info("Schedulers stopped")


def _check_and_retrain_on_startup() -> None:
    """Retrain models on startup if they are stale (> 24 hours old) or absent."""
    model_file = ARTIFACT_DIR / "xgb_classifier.joblib"
    if not model_file.exists():
        logger.info("No model artifacts found — training on startup")
        _do_retrain()
        return
    age_hours = (time.time() - model_file.stat().st_mtime) / 3600
    if age_hours > 24:
        logger.info("Model artifacts are %.1f hours old — retraining on startup", age_hours)
        _do_retrain()
    else:
        logger.info("Model artifacts are %.1f hours old — using existing models", age_hours)


def _do_retrain() -> None:
    """Run the training pipeline and reload models."""
    global _ml_detector
    try:
        import importlib
        from backend.src.anomaly_detection.ml import train
        importlib.reload(train)
        train.train()
        logger.info("Startup retrain complete")
    except Exception as exc:
        logger.error("Startup retrain failed: %s", exc, exc_info=True)
    finally:
        if _ml_detector is not None:
            _ml_detector._loaded = _ml_detector._load_models()
            logger.info("ML detector reloaded models after retrain")


def _run_ml_detection() -> None:
    global _ml_detector
    try:
        if _ml_detector is None:
            _ml_detector = MLAnomalyDetector()
        _ml_detector.detect_and_save()
    except Exception as exc:
        logger.error("ML detection cycle failed: %s", exc, exc_info=True)


def _auto_retrain() -> None:
    """Retrain ML models if they are stale (> 24 hours old).

    Fires every 1h via scheduler. Guards against retraining if the model
    was already retrained recently (e.g., on startup).
    Trains on LIVE generator data by default.
    Set USE_OFFLINE_DATA=true env var to use the offline training dataset instead.
    """
    import os
    use_offline = os.getenv("USE_OFFLINE_DATA", "false").lower() == "true"
    logger.info("Auto-retrain triggered (%s)", "OFFLINE dataset" if use_offline else "LIVE generator data")
    model_file = ARTIFACT_DIR / "xgb_classifier.joblib"
    if model_file.exists():
        age_hours = (time.time() - model_file.stat().st_mtime) / 3600
        if age_hours <= 24:
            logger.info("Auto-retrain skipped — models are %.1f hours old", age_hours)
            return
    logger.info("Auto-retrain triggered — models are stale")
    _do_retrain()


app = FastAPI(title="ATM Log Aggregation Platform", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
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
