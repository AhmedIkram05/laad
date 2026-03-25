"""FastAPI web server entry point.

Run with:
    uvicorn backend.api.server:app --reload --port 8000
"""
from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware

from backend.src.auth.router import router as authRouter, getCurrentUser, requireAdmin

app = FastAPI(title="ATM Log Aggregation Platform")

# CORS — allows the frontend dev server (localhost:5173) to talk to the API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
app.include_router(authRouter)

# All other routers get added here as we build them, e.g.:
# app.include_router(anomaliesRouter)
# app.include_router(eventsRouter)
