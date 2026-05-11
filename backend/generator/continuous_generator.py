"""Continuous synthetic log generator.

Emits baseline events every TICK_SECONDS and injects anomalies probabilistically.
Backfills DB on startup (no anomalies), then enters live loop with anomaly injection.

Usage:
    python -m backend.generator.continuous_generator
"""
from __future__ import annotations

import logging
import os
import random
import signal
import time
from datetime import datetime, timedelta, timezone

from dotenv import load_dotenv

from backend.src.database.connection import get_cursor
from backend.generator.config import (
    TICK_SECONDS, BACKFILL_MINUTES, ANOMALY_PROB, GENERATOR_SEED, ATMS
)
from backend.generator.emitters import BASELINE_EMITTERS
from backend.generator.anomaly_injectors import ANOMALY_REGISTRY

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s [GENERATOR] %(message)s")
log = logging.getLogger(__name__)

_shutdown_requested = False
_in_backfill = False

def _graceful_shutdown(signum, frame):
    global _shutdown_requested
    log.info("Shutdown signal received — stopping generator...")
    _shutdown_requested = True

signal.signal(signal.SIGTERM, _graceful_shutdown)
signal.signal(signal.SIGINT, _graceful_shutdown)

seed_val = int(GENERATOR_SEED) if GENERATOR_SEED else None
rng = random.Random(seed_val)

def now_utc() -> datetime:
    return datetime.now(timezone.utc)

def emit_tick(t: datetime, anomaly_last_seen: dict[str, datetime]) -> None:
    """Emit one full tick of baseline events and probabilistically inject anomalies."""
    with get_cursor(commit=True) as cur:
        for emitter in BASELINE_EMITTERS:
            try:
                emitter(cur, t)
            except Exception as exc:
                log.warning("Emitter %s failed: %s", emitter.__name__, exc)

        if not _in_backfill and rng.random() < ANOMALY_PROB:
            eligible = [
                (name, fn, cooldown)
                for name, fn, cooldown in ANOMALY_REGISTRY
                if (t - anomaly_last_seen.get(name, datetime.min.replace(tzinfo=timezone.utc))).total_seconds() >= cooldown
            ]
            if eligible:
                name, fn, _ = rng.choice(eligible)
                try:
                    fn(cur, t)
                    anomaly_last_seen[name] = t
                    log.info("Injected anomaly %s", name)
                except Exception as exc:
                    log.warning("Anomaly injector %s failed: %s", name, exc)

def backfill(minutes: int) -> None:
    """Seed DB with `minutes` of historical data.

    Backfill includes a small anomaly injection rate so training data
    contains both normal windows and labelled anomalies. This gives
    Isolation Forest normal baselines AND XGBoost labelled examples to learn from.
    """
    global _in_backfill

    if minutes <= 0:
        log.info("Backfill skipped (BACKFILL_MINUTES=0)")
        return

    log.info("Backfilling %d minutes of historical data...", minutes)
    _in_backfill = True

    backfill_prob = 0.01
    import backend.generator.config as cfg
    saved_prob = cfg.ANOMALY_PROB
    cfg.ANOMALY_PROB = backfill_prob
    log.info("Anomaly injection during backfill: %.4f (live: %.4f)", backfill_prob, saved_prob)

    start = now_utc() - timedelta(minutes=minutes)
    anomaly_last: dict[str, datetime] = {}
    step = timedelta(seconds=TICK_SECONDS)
    t = start
    count = 0

    while t < now_utc() and not _shutdown_requested:
        try:
            emit_tick(t, anomaly_last)
        except Exception as exc:
            log.warning("Backfill tick at %s failed: %s — continuing", t, exc)
        t += step
        count += 1

    _in_backfill = False
    cfg.ANOMALY_PROB = saved_prob
    log.info("Backfill complete (%d ticks, live anomaly prob: %.4f)", count, saved_prob)

def main() -> None:
    """Entry point: backfill, then live loop forever."""
    log.info("Starting continuous log generator (tick=%ds, backfill=%dmin, anomaly_prob=%.4f, seed=%s)",
            TICK_SECONDS, BACKFILL_MINUTES, ANOMALY_PROB, GENERATOR_SEED or "random")

    backfill(BACKFILL_MINUTES)

    if _shutdown_requested:
        return

    log.info("Entering live generation loop...")
    anomaly_last: dict[str, datetime] = {}
    backoff = TICK_SECONDS
    while not _shutdown_requested:
        t = now_utc()
        try:
            emit_tick(t, anomaly_last)
            backoff = TICK_SECONDS
        except Exception as exc:
            log.error("Tick failed: %s", exc, exc_info=True)
            backoff = min(60, backoff * 2)
        time.sleep(backoff)

if __name__ == "__main__":
    main()