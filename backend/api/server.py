"""FastAPI web server entry point.

Run with:
    uvicorn backend.api.server:app --reload --port 8000
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.src.auth.auth_router import router as authRouter
from backend.src.admin.admin_router import router as adminRouter
from backend.src.admin.cleanup import runCleanup

logger = logging.getLogger(__name__)

scheduler = BackgroundScheduler()


@asynccontextmanager
async def lifespan(app: FastAPI):
    scheduler.add_job(runCleanup, "interval", hours=6, id="cleanup")
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

# -- Routers --
app.include_router(authRouter)
app.include_router(adminRouter)