-- ==================================================================================
-- LOG AGGREGATION & DIAGNOSTICS DB SCHEMA
-- This database schema uses a unified 'Data Lake' style approach to simplify schema
-- maintenance and make cross-correlation much easier for the detection engine.
-- It works with SQLite and can be extended to PostgreSQL later on, if needed.
-- ==================================================================================

-- 1. REFERENCE TABLE: atms
-- Holds the basic, static information about the physical ATM terminals.
-- Note: Slowly changing dimensions like os_version, app_version, and hostname 
-- should be extracted dynamically from the events/metrics payload at query time
-- to preserve the historical state of the ATM during a specific anomaly.
CREATE TABLE IF NOT EXISTS atms (
    atm_id TEXT PRIMARY KEY,        -- Unique ATM identifier (e.g., 'ATM-GB-0042')
    location_code TEXT              -- Physical location code (e.g., 'LOC-0117')
);

-- 2. THE UNIFIED 'EVENTS' TABLE
-- Combines discrete logs (ATM App Logs, Terminal Handler Logs, Hardware Sensor Logs).
-- Critical keys are strict columns; the rest goes into the JSON 'payload'.
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp DATETIME NOT NULL,    -- UTC event time (e.g., '2026-03-05T09:14:33.221Z')
    source TEXT NOT NULL,           -- Origin system ('ATM_APP', 'TERMINAL_HANDLER', 'HARDWARE')
    atm_id TEXT,                    -- The ATM unit (e.g., 'ATM-GB-0042')
    correlation_id TEXT,            -- Transaction trace ID (links across all sources)
    transaction_id TEXT,            -- Banking transaction UUID (ATM App, Terminal Handler, Kafka)
    event_type TEXT,                -- Categorised trigger (e.g., 'TRANSACTION_END', 'TIMEOUT')
    severity TEXT,                  -- Status ('INFO', 'ERROR', 'CRITICAL')
    message TEXT,                   -- Human-readable message (e.g., 'Amount dispensed: 200.00')
    payload TEXT                    -- Original JSON full payload (e.g., '{"component":"CashDispenser"}')
);

-- 3. THE UNIFIED 'METRICS' TABLE
-- Combines continuous time-series data (OS, GCP Cloud/Prometheus, Kafka Streams).
CREATE TABLE IF NOT EXISTS metrics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp DATETIME NOT NULL,    -- UTC snapshot time (e.g., '2026-03-05T09:15:00Z')
    source TEXT NOT NULL,           -- Telemetry provider ('OS', 'CLOUD', 'KAFKA')
    entity_id TEXT NOT NULL,        -- Target ID ('ATM-GB-0042', 'auth-service-pod-123')
    metric_name TEXT NOT NULL,      -- Measurement name ('cpu_usage_percent', 'memory_used_mb')
    metric_value REAL NOT NULL,     -- The numeric measurement (e.g., 84.5)
    payload TEXT                    -- Tags/dimensions in JSON (e.g., '{"cluster_name":"atm-core"}')
);

-- 4. ANOMALIES
-- Tracks system-flagged problems to populate the frontend dashboard.
-- recommended_action is NOT stored here — it is joined from the
-- recommendations table at query time so templates can be updated centrally.
CREATE TABLE IF NOT EXISTS anomalies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    detected_at DATETIME NOT NULL,      -- UTC detection time
    anomaly_type TEXT NOT NULL,         -- Standard issue type (e.g., 'A1', 'A2')
    atm_id TEXT REFERENCES atms(atm_id),
    correlation_id TEXT,                -- Optional isolated transaction UUID
    model_confidence_score REAL,        -- e.g., 0.95 (How confident the AI is about this prediction)
    severity TEXT NOT NULL,             -- Severity level ('HIGH', 'CRITICAL')
    title TEXT NOT NULL,                -- UI display string
    explanation TEXT NOT NULL,          -- Detailed reason with specific field values
    sources_involved TEXT,              -- JSON array of sources e.g. '["ATM_APP","KAFKA"]'
    evidence_event_ids TEXT,            -- JSON array of event IDs that triggered this
    evidence_metric_ids TEXT,           -- JSON array of metric IDs that triggered this
    is_active INTEGER DEFAULT 1         -- 1 = Current/Unresolved, 0 = Resolved
);

-- 5. RECOMMENDATION TEMPLATES
-- One row per anomaly type (A1-A7), seeded at startup.
-- Joined to anomalies at query time — updating one row here updates
-- all future recommendations of that type (satisfies Extensibility NFR).
CREATE TABLE IF NOT EXISTS recommendations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    anomaly_type TEXT NOT NULL UNIQUE,  -- 'A1' through 'A7'
    root_cause TEXT NOT NULL,           -- Plain-English probable cause
    actions TEXT NOT NULL               -- JSON array of recommended next actions
);

-- 6. FEEDBACK
-- Separate table (not a column on anomalies) because one anomaly can
-- receive multiple feedback entries over time. The Like/Dislike ratio
-- is computed at query time from this table.
CREATE TABLE IF NOT EXISTS feedback (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    anomaly_id INTEGER NOT NULL REFERENCES anomalies(id),
    rating TEXT NOT NULL,               -- 'LIKE' or 'DISLIKE'
    submitted_at DATETIME NOT NULL      -- UTC submission time
);

-- 7. INGESTION ERRORS
-- Ensures un-parseable JSON or corrupted data is saved for review.
-- Powers the Data Health dashboard panel (NFR1, NFR2).
CREATE TABLE IF NOT EXISTS ingestion_errors (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp DATETIME NOT NULL,        -- UTC failure time
    source TEXT NOT NULL,               -- Intended source ('HARDWARE', 'OS', etc.)
    error_detail TEXT NOT NULL,         -- What went wrong
    raw_input TEXT                      -- The corrupted payload string
);

-- ==============================================================================
-- INDEXES FOR FASTER SEARCHING
-- Kept to the most common use cases
-- ==============================================================================

-- Events: allow fast lookups by correlation id when tracing a transaction across sources
CREATE INDEX IF NOT EXISTS idx_events_correlation   ON events(correlation_id);

-- Events: speed up timeline queries for a specific ATM (powers the main ATM drilldown UI)
CREATE INDEX IF NOT EXISTS idx_events_atm_time      ON events(atm_id, timestamp);

-- Events: quick lookup by banking transaction id across sources
CREATE INDEX IF NOT EXISTS idx_events_transaction   ON events(transaction_id);

-- Metrics: speed up time-range retrievals for a single entity (pod or ATM)
CREATE INDEX IF NOT EXISTS idx_metrics_entity_time  ON metrics(entity_id, timestamp);

-- Metrics: optimise queries that filter by metric name over a time window
-- (Note: Also covers plain metric_name searches via index left-prefixing)
CREATE INDEX IF NOT EXISTS idx_metrics_name_time    ON metrics(metric_name, timestamp);

-- Anomalies: quick drilldown for a single ATM's recorded anomalies
CREATE INDEX IF NOT EXISTS idx_anomalies_atm        ON anomalies(atm_id);

-- Anomalies: optimise the main dashboard view ("Show me ACTIVE issues, newest first")
CREATE INDEX IF NOT EXISTS idx_anomalies_active_time ON anomalies(is_active, detected_at);

-- Feedback: accelerate lookups of user feedback for a given anomaly (1-to-Many JOIN)
CREATE INDEX IF NOT EXISTS idx_feedback_anomaly     ON feedback(anomaly_id);