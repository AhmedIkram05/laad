"""FastAPI web server entry point.

Run with:
    uvicorn backend.api.server:app --reload --port 8000
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from backend.src.admin.cleanup import run_cleanup
from backend.src.admin.admin_router import router as adminRouter
from backend.src.anomalies.anomalies_router import router as anomaliesRouter
from backend.src.atms.atms_router import router as atmsRouter
from backend.src.auth.auth_router import router as authRouter
from backend.src.events.events_router import router as eventsRouter
from backend.src.metrics.metrics_router import router as metricsRouter
from backend.src.timeline.timeline_router import router as timelineRouter
from backend.src.analysis_router.analysis_router import router as analysisRouter

logger = logging.getLogger(__name__)

scheduler = BackgroundScheduler()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manages scheduler startup and shutdown."""
    scheduler.add_job(run_cleanup, "interval", hours=6, id="cleanup")
    scheduler.start()
    logger.info("Cleanup scheduler started (interval: 6h)")
    yield
    scheduler.shutdown()
    logger.info("Cleanup scheduler stopped")


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
app.include_router(atmsRouter)
app.include_router(eventsRouter)
app.include_router(metricsRouter)
app.include_router(timelineRouter)
app.include_router(analysisRouter)