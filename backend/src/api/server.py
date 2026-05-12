"""FastAPI web server entry point.

Run with:
    uvicorn backend.src.api.server:app --reload --port 8000
"""
from __future__ import annotations

import logging
import time
from contextlib import asynccontextmanager

from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from backend.src.admin.cleanup import run_cleanup
from backend.src.admin.admin_router import router as adminRouter
from backend.src.anomalies.anomalies_router import router as anomaliesRouter
from backend.src.auth.auth_router import router as authRouter
from backend.src.analysis.analysis_router import router as analysisRouter
from backend.src.database.init_db import init_db

logger = logging.getLogger(__name__)

scheduler = BackgroundScheduler()

_ml_detector = None
_db_initialized = False


def _ensure_db_initialized():
    """Ensure database is seeded. Called on startup and first request."""
    global _db_initialized
    if _db_initialized:
        return
    
    max_retries = 3
    for attempt in range(1, max_retries + 1):
        try:
            print(f"[INIT_DB] Attempt {attempt}/{max_retries}: Seeding database...")
            init_db()
            _db_initialized = True
            logger.info("✓ Database seeded successfully")
            print("[INIT_DB] ✓ Database seeded successfully")
            return
        except Exception as e:
            error_msg = f"Failed to seed database (attempt {attempt}/{max_retries}): {str(e)}"
            print(f"[INIT_DB] {error_msg}")
            logger.exception(error_msg)
            if attempt < max_retries:
                time.sleep(2)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manages scheduler startup and shutdown."""
    # Seed database on startup
    print("[LIFESPAN] Starting up... initializing database")
    _ensure_db_initialized()
    
    scheduler.add_job(run_cleanup, "interval", hours=1, id="cleanup")
    scheduler.add_job(_run_ml_detection, "interval", seconds=10, id="ml_detector")
    scheduler.start()
    logger.info("✓ Cleanup scheduler started (interval: 1h)")
    logger.info("✓ ML anomaly detector scheduler started (interval: 10s)")
    print("[LIFESPAN] Startup complete")
    yield
    scheduler.shutdown()
    logger.info("Schedulers stopped")


def _run_ml_detection():
    global _ml_detector
    try:
        from backend.src.anomaly_detection.ml.ml_detector import MLAnomalyDetector
        if _ml_detector is None:
            _ml_detector = MLAnomalyDetector()
        _ml_detector.detect_and_save()
    except Exception as exc:
        logger.error("ML detection cycle failed: %s", exc, exc_info=True)


app = FastAPI(title="ATM Log Aggregation Platform", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(Exception)
async def globalExceptionHandler(request: Request, exc: Exception):
    """Catches unhandled exceptions and returns clean JSON instead of
    leaking raw stack traces to the frontend.
    """
    logger.error(f"Unhandled exception on {request.url}: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": "An internal server error occurred"}
    )


# Routers — one line per domain
app.include_router(authRouter)
app.include_router(adminRouter)
app.include_router(anomaliesRouter)
app.include_router(analysisRouter)