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
from backend.src.rag.router import router as ragRouter
from backend.src.database.connection import get_conn, release_conn
from backend.src.database.init_db import init_db
from backend.src.anomaly_detection.ml.train import ARTIFACT_DIR

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
        joblib.load(model_file)
        joblib.load(ARTIFACT_DIR / "isolation_forest.joblib")
        joblib.load(ARTIFACT_DIR / "label_encoder.joblib")
        logger.info("Model artifacts are valid — using existing models")
        return
    except Exception as e:
        logger.warning("Model artifacts exist but are corrupted or incompatible: %s — retraining", e)
    
    logger.info("No valid model artifacts found — training on startup")
    _do_retrain()


def _do_retrain() -> None:
    """Run the training pipeline."""
    try:
        import importlib
        from backend.src.anomaly_detection.ml import train
        importlib.reload(train)
        train.train()
        logger.info("Startup retrain complete")
    except Exception as exc:
        logger.error("Startup retrain failed: %s", exc, exc_info=True)


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
app.include_router(ragRouter)
