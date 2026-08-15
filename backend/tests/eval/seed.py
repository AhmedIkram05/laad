"""Deterministic eval seed for the RAG agent golden set.

Populates the test database (atm_platform_test) and the Chroma `atm_logs`
collection with fixed, queryable fixtures. Golden queries in golden_set.json
are only answerable from this data.

Run inside the pytest container:
    docker compose run --rm pytest sh -c "PYTHONPATH=/app python backend/tests/eval/seed.py"
"""
import os
from datetime import datetime, timedelta, timezone

# Replicate conftest's env override so we hit the same DB the tests use.
if os.path.exists("/.dockerenv"):
    os.environ.setdefault("POSTGRES_HOST", "host.docker.internal")
os.environ.setdefault("POSTGRES_PORT", "5433")
os.environ.setdefault("POSTGRES_DB", "atm_platform_test")
os.environ.setdefault("POSTGRES_USER", "atm_user")
os.environ.setdefault("POSTGRES_PASSWORD", "your_password_here")

from backend.src.database.connection import get_conn  # noqa: E402
from backend.src.database.init_db import init_db  # noqa: E402
from backend.kafka.chroma_buffer import (  # noqa: E402
    COLLECTION_NAME,
    _build_chroma_client,
    _build_embeddings,
    _build_chunker,
)

NOW = datetime.now(timezone.utc)


def _ts(hours_ago: float) -> str:
    return (NOW - timedelta(hours=hours_ago)).isoformat()


# --- Chroma docs ---------------------------------------------------------
# Each scenario's log text embeds remediation knowledge: chroma is the ONLY
# source search_knowledge has (knowledge.py curated classes are NOT wired in).
SCENARIOS = [
    {
        "atm_id": "ATM-GB-0001",
        "anomaly_tag": "A1",
        "severity": "FATAL",
        "lines": [
            "2026-08-14T10:02:11Z [HARDWARE] HARDWARE_FAULT: dispenser motor failure error_code=ERR-0077 part=dispenser | dispatch field engineer, check component diagnostics and part inventory",
            "2026-08-14T10:02:13Z [ATM_APP] DEVICE_OFFLINE: card reader unresponsive retries=5 error_code=ERR-0021 | physical hardware component failure, device offline, repeated retries",
            "2026-08-14T10:02:15Z [ATM_APP] SENSOR_ALARM: cash sensor reading abnormal sensor=rear_sensor | component error codes, check sensors",
        ],
    },
    {
        "atm_id": "ATM-GB-0001",
        "anomaly_tag": "A3",
        "severity": "ERROR",
        "lines": [
            "2026-08-14T09:40:00Z [OS] NETWORK_DEGRADED: link flapping on eth0 packet_loss=18% | check link status, firewall and TLS config, ping and traceroute from ATM",
            "2026-08-14T09:42:00Z [PROMETHEUS] CONNECTION_TIMEOUT: backend API unreachable timeout_ms=30000 | connectivity degradation or loss between ATM and backend",
        ],
    },
    {
        "atm_id": "ATM-GB-0003",
        "anomaly_tag": "A4",
        "severity": "ERROR",
        "lines": [
            "2026-08-14T08:15:00Z [ATM_APP] DISPENSE_ERROR: cash dispense failed count_mismatch=2 error_code=ERR-0101 | reconcile cassette counts, run dispense self-test before redeploying cash",
            "2026-08-14T08:15:01Z [TERMINAL_HANDLER] CASSETTE_ALARM: cassette 3 low/empty alarm | cassette issues, currency mismatch, dispense failures",
        ],
    },
    {
        "atm_id": "ATM-GB-0005",
        "anomaly_tag": "A5",
        "severity": "CRITICAL",
        "lines": [
            "2026-08-14T07:05:00Z [ATM_APP] AUTH_FAILURE_BURST: 40 failed auth attempts in 5 minutes | possible skimming, failed auth bursts, unusual access patterns",
            "2026-08-14T07:05:30Z [CLOUD] TAMPER_EVENT: tamper switch triggered on front panel | escalate to security, freeze affected services, preserve evidence logs",
        ],
    },
    {
        "atm_id": "ATM-GB-0007",
        "anomaly_tag": "A7_MALFORMED",
        "severity": "ERROR",
        "lines": [
            "2026-08-14T06:30:00Z [KAFKA] SCHEMA_VIOLATION: event rejected schema_version=2 error=missing_field transaction_id | check producer/consumer offsets, validate payload schema, replay from last good offset",
            "2026-08-14T06:31:00Z [ATM_APP] SEQ_GAP: sequence gap detected expected=4411 got=4418 | events arriving out of order or malformed, sequence gaps",
        ],
    },
    {
        "atm_id": "ATM-GB-0009",
        "anomaly_tag": "A2",
        "severity": "ERROR",
        "lines": [
            "2026-08-14T05:55:00Z [ATM_APP] PROCESS_RESTART: app crashed and restarted pid=8821 | application-level crash, exception storm or process restart, startup failures",
            "2026-08-14T05:55:05Z [OS] EXCEPTION_STORM: java.lang.OutOfMemoryError repeated x12 | collect crash logs and traceback, correlate with deployment window",
        ],
    },
]

# --- DB fixtures ---------------------------------------------------------
# anomalies: (atm_id, anomaly_type, severity, hours_ago, title, explanation, action)
ANOMALIES = [
    ("ATM-GB-0001", "A1", "ERROR", 2.0,
     "Hardware failure: dispenser offline",
     "Dispenser motor failure and card reader offline detected on ATM-GB-0001.",
     "Dispatch field engineer; check component diagnostics and part inventory."),
    ("ATM-GB-0001", "A3", "ERROR", 3.5,
     "Network timeouts detected",
     "Packet loss and backend API timeouts observed; link flapping on eth0.",
     "Check link status, firewall and TLS config; ping and traceroute from ATM."),
    ("ATM-GB-0003", "A4", "ERROR", 5.0,
     "Cash dispense error",
     "Dispense failure with cassette count mismatch on ATM-GB-0003.",
     "Reconcile cassette counts; run dispense self-test before redeploying cash."),
    ("ATM-GB-0005", "A5", "CRITICAL", 7.0,
     "Possible skimming detected",
     "Failed auth burst followed by tamper switch event on ATM-GB-0005.",
     "Escalate to security; freeze affected services; preserve evidence logs."),
    ("ATM-GB-0007", "A7", "ERROR", 9.0,
     "Malformed kafka event",
     "Kafka event rejected by schema validation; sequence gap detected.",
     "Check producer/consumer offsets; validate payload schema; replay from last good offset."),
    ("ATM-GB-0009", "A2", "ERROR", 11.0,
     "App crash loop",
     "Application crashed and restarted repeatedly with OutOfMemoryError.",
     "Collect crash logs and traceback; correlate with deployment window."),
]

# metrics: (entity_id, metric_name, hours_ago, value)
METRICS = [
    ("ATM-GB-0001", "jvm_memory_used_bytes", 1.0, 805306368),
    ("ATM-GB-0001", "jvm_memory_used_bytes", 0.5, 943718400),
    ("ATM-GB-0001", "jvm_memory_used_bytes", 0.1, 1015021568),
    ("ATM-GB-0001", "network_errors", 1.0, 12),
    ("ATM-GB-0001", "network_errors", 0.1, 27),
    ("ATM-GB-0001", "process_cpu_usage", 1.0, 0.35),
    ("ATM-GB-0001", "process_cpu_usage", 0.1, 0.62),
    ("ATM-GB-0003", "container/restart_count", 1.0, 3),
    ("ATM-GB-0003", "container/restart_count", 0.1, 5),
    ("ATM-SERVER-001", "memory_usage_percent", 1.0, 71.5),
    ("ATM-SERVER-001", "memory_usage_percent", 0.1, 74.2),
]

# events: (source, event_type, severity, hours_ago, message, atm_id)
EVENTS = [
    ("HARDWARE", "HARDWARE_FAULT", "FATAL", 2.0,
     "dispenser motor failure error_code=ERR-0077", "ATM-GB-0001"),
    ("ATM_APP", "NETWORK_TIMEOUT", "ERROR", 3.5,
     "backend API timeout response_time_ms=30000", "ATM-GB-0001"),
    ("TERMINAL_HANDLER", "CASSETTE_ALARM", "ERROR", 5.0,
     "cassette 3 count mismatch", "ATM-GB-0003"),
    ("ATM_APP", "TAMPER_ALERT", "CRITICAL", 7.0,
     "tamper switch triggered", "ATM-GB-0005"),
    ("KAFKA", "SCHEMA_VIOLATION", "ERROR", 9.0,
     "event rejected missing_field=transaction_id", "ATM-GB-0007"),
]


def _seed_db() -> None:
    conn = get_conn()
    try:
        cur = conn.cursor()
        for atm_id, a_type, severity, hours_ago, title, expl, action in ANOMALIES:
            cur.execute(
                """INSERT INTO anomalies (detected_at, anomaly_type, atm_id, severity,
                       title, explanation, recommended_action, is_active, model_confidence_score)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, 1, 0.94)
                   ON CONFLICT DO NOTHING""",
                (_ts(hours_ago), a_type, atm_id, severity, title, expl, action),
            )
        for entity, metric, hours_ago, value in METRICS:
            cur.execute(
                """INSERT INTO metrics (timestamp, source, entity_id, metric_name, metric_value)
                   VALUES (%s, %s, %s, %s, %s) ON CONFLICT DO NOTHING""",
                (_ts(hours_ago), "eval-seed", entity, metric, value),
            )
        for source, etype, severity, hours_ago, message, atm_id in EVENTS:
            cur.execute(
                """INSERT INTO events (timestamp, source, atm_id, event_type, severity, message, payload)
                   VALUES (%s, %s, %s, %s, %s, %s, '{}') ON CONFLICT DO NOTHING""",
                (_ts(hours_ago), source, atm_id, etype, severity, message),
            )
        conn.commit()
        print(f"seeded: {len(ANOMALIES)} anomalies, {len(METRICS)} metrics, {len(EVENTS)} events")
    finally:
        conn.close()


def _seed_chroma() -> None:
    client = _build_chroma_client()
    # Non-destructive: NEVER delete+recreate here. Deleting swaps the
    # collection UUID and strands the retriever singleton of any OTHER
    # process (e.g. a concurrently running eval) on a 404'd collection.
    # Deterministic ids make upsert idempotent, so re-seeding is a no-op.
    collection = client.get_or_create_collection(
        COLLECTION_NAME, metadata={"hnsw:space": "cosine"}
    )
    embeddings = _build_embeddings()
    chunker = _build_chunker(embeddings)
    docs, metas, ids = [], [], []
    for sc in SCENARIOS:
        text = "\n".join(f"ATM: {sc['atm_id']} | {line}" for line in sc["lines"])
        chunks = chunker.create_documents([text])
        for i, c in enumerate(chunks):
            docs.append(c.page_content)
            metas.append({
                "atm_id": sc["atm_id"],
                "_anomaly_tag": sc["anomaly_tag"],
                "severity": sc["severity"],
                "last_timestamp": _ts(1.0),
            })
            ids.append(f"{sc['atm_id']}_{sc['anomaly_tag']}_{i}")
    collection.upsert(documents=docs, ids=ids, metadatas=metas)
    print(f"seeded chroma: {len(docs)} chunks across {len(SCENARIOS)} scenarios")


def main() -> None:
    init_db(force=True)
    _seed_db()
    _seed_chroma()
    print("eval seed complete")


if __name__ == "__main__":
    main()