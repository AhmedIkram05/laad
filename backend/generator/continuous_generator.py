"""Continuous synthetic log generator.

Emits baseline events every TICK_SECONDS and injects anomalies probabilistically.
Backfills DB on startup (no anomalies), then enters live loop with anomaly injection.

All data is written via Kafka — no direct DB writes from this module.
The only DB call is seed_atm_fleet() which ensures ATM records exist for FK constraints.

Usage:
    python -m backend.generator.continuous_generator
"""

from __future__ import annotations

import logging
import random
import signal
import time
from datetime import datetime, timedelta, timezone

from dotenv import load_dotenv

from backend.generator.config import (
    TICK_SECONDS,
    BACKFILL_MINUTES,
    ANOMALY_PROB,
    GENERATOR_SEED,
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


def emit_tick(
    producer,
    t: datetime,
    anomaly_last_seen: dict[str, datetime],
    backfill_mode: bool = False,
    backfill_prob: float = 0.01,
) -> None:
    for emitter in BASELINE_EMITTERS:
        try:
            emitter(producer, t)
        except Exception as exc:
            log.warning("Emitter %s failed: %s", emitter.__name__, exc)

    prob_threshold = backfill_prob if backfill_mode else ANOMALY_PROB
    if not backfill_mode and rng.random() < prob_threshold:
        eligible = [
            (name, fn, cooldown)
            for name, fn, cooldown in ANOMALY_REGISTRY
            if (
                t
                - anomaly_last_seen.get(name, datetime.min.replace(tzinfo=timezone.utc))
            ).total_seconds()
            >= cooldown
        ]
        if eligible:
            name, fn, _ = rng.choice(eligible)
            try:
                atm_id = fn(producer, t)
                anomaly_last_seen[name] = t
                log.info("Injected anomaly %s on %s", name, atm_id)
            except Exception as exc:
                log.warning("Anomaly injector %s failed: %s", name, exc)

    producer.flush()


def backfill(producer, minutes: int) -> None:
    global _in_backfill

    if minutes <= 0:
        log.info("Backfill skipped (BACKFILL_MINUTES=0)")
        return

    log.info("Backfilling %d minutes of historical data...", minutes)
    _in_backfill = True

    backfill_prob = 0.01
    log.info(
        "Anomaly injection during backfill: %.4f (live: %.4f)",
        backfill_prob,
        ANOMALY_PROB,
    )

    start = now_utc() - timedelta(minutes=minutes)
    anomaly_last: dict[str, datetime] = {}
    step = timedelta(seconds=TICK_SECONDS)
    t = start
    count = 0

    while t < now_utc() and not _shutdown_requested:
        try:
            emit_tick(
                producer,
                t,
                anomaly_last,
                backfill_mode=True,
                backfill_prob=backfill_prob,
            )
        except Exception as exc:
            log.warning("Backfill tick at %s failed: %s — continuing", t, exc)
        t += step
        count += 1

    _in_backfill = False
    log.info(
        "Backfill complete (%d ticks, live anomaly prob: %.4f)", count, ANOMALY_PROB
    )


def main() -> None:
    from backend.kafka.producer import get_producer
    from backend.src.database.init_db import seed_atm_fleet
    from backend.src.database.connection import get_cursor

    log.info(
        "Starting continuous log generator (tick=%ds, backfill=%dmin, anomaly_prob=%.4f, seed=%s)",
        TICK_SECONDS,
        BACKFILL_MINUTES,
        ANOMALY_PROB,
        GENERATOR_SEED or "random",
    )

    producer = get_producer()

    with get_cursor(commit=True) as cur:
        cur.execute("SELECT COUNT(*) FROM atms")
        count = list(cur.fetchone().values())[0]
        if count == 0:
            seed_atm_fleet()

    backfill(producer, BACKFILL_MINUTES)

    if _shutdown_requested:
        producer.close()
        return

    log.info("Entering live generation loop...")
    anomaly_last: dict[str, datetime] = {}

    while not _shutdown_requested:
        t = now_utc()
        try:
            emit_tick(producer, t, anomaly_last)
            backoff = TICK_SECONDS
        except Exception as exc:
            log.error("Tick failed: %s", exc, exc_info=True)
            backoff = min(60, backoff * 2)
        time.sleep(backoff)


if __name__ == "__main__":
    main()
