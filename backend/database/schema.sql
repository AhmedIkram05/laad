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
    os_version TEXT,                -- Operating system version
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
    recommended_action TEXT,            -- Recommended next action logic
    sources_involved TEXT,              -- JSON array of sources e.g. '["ATM_APP","KAFKA"]'
    feedback_rating TEXT,               -- 'LIKE' or 'DISLIKE' or NULL
    is_active INTEGER DEFAULT 1         -- 1 = Current/Unresolved, 0 = Resolved
);

-- 5. INGESTION ERRORS
-- Ensures un-parseable JSON or corrupted data is saved for review.
-- Powers the Data Health dashboard panel (NFR1, NFR2).
CREATE TABLE IF NOT EXISTS ingestion_errors (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp DATETIME NOT NULL,        -- UTC failure time
    source TEXT NOT NULL,               -- Intended source ('HARDWARE', 'OS', etc.)
    error_detail TEXT NOT NULL,         -- What went wrong
    raw_input TEXT                      -- The corrupted payload string
);

-- ======================================================================
-- AUTH / RETENTION: permanent users, one-time tokens, and retention config
-- These tables power the FastAPI auth router and a single-row retention
-- configuration that can be adjusted by admins in future work.
-- ======================================================================

-- AUTH: Permanent user accounts
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'user' CHECK (role IN ('admin', 'user')),
    created_at DATETIME NOT NULL DEFAULT (datetime('now'))
);

-- AUTH: One-time access tokens (admin generates OTP in settings --> sends to guest)
CREATE TABLE IF NOT EXISTS otp_tokens (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    token TEXT NOT NULL UNIQUE,
    role TEXT NOT NULL DEFAULT 'user' CHECK (role IN ('admin', 'user')),
    created_by INTEGER REFERENCES users(id),
    created_at DATETIME NOT NULL DEFAULT (datetime('now')),
    expires_at DATETIME NOT NULL,
    used_at DATETIME                -- NULL = not yet redeemed
);

-- ==============================================================================
-- INDEXES FOR FASTER SEARCHING
-- Kept to the most common use cases
-- ==============================================================================

-- Indexes for auth tables
CREATE INDEX IF NOT EXISTS idx_otp_token ON otp_tokens(token);
CREATE INDEX IF NOT EXISTS idx_users_username ON users(username);

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

-- ========================================================================
-- FLATTENED VIEWS FOR ANALYSIS / FRONTEND
-- These views provide a denormalised, query-friendly shape for analysts
-- and the frontend without changing the ingestion writers.
-- ========================================================================

-- 6. FLATTENED EVENT VIEW (v_events_flat)
-- Extracts and normalises common fields from the payload JSON for all discrete events.
-- This ensures analysts can query ATM status, error codes, and response times 
-- as first-class columns rather than digging into the raw JSON payload.
DROP VIEW IF EXISTS v_events_flat;
CREATE VIEW v_events_flat AS
SELECT
    e.id AS event_id_internal,
    e.timestamp,
    e.source,
    e.atm_id,
    COALESCE(e.correlation_id, json_extract(e.payload, '$.correlation_id'), json_extract(e.payload, '$.trace_id')) AS correlation_id,
    e.transaction_id,
    e.event_type,
    e.severity,
    e.message,
    json_extract(e.payload, '$.location_code') AS location_code,
    json_extract(e.payload, '$.response_time_ms') AS response_time_ms,
    COALESCE(json_extract(e.payload, '$.error_code'), json_extract(e.payload, '$.transaction_failure_reason')) AS error_code,
    json_extract(e.payload, '$.exception_class') AS exception_class,
    COALESCE(json_extract(e.payload, '$.error_detail'), json_extract(e.payload, '$.exception_message')) AS error_detail,
    COALESCE(json_extract(e.payload, '$.component'), json_extract(e.payload, '$.service_name'), json_extract(e.payload, '$.sensor_type')) AS component,
    COALESCE(json_extract(e.payload, '$.http_status_code'), json_extract(e.payload, '$.atm_status')) AS atm_status,
    e.payload AS raw_payload
FROM events e;

-- 7. FLATTENED METRICS VIEW (v_metrics_flat)
-- Expands continuous time-series metrics into the same columnar shape as events.
-- Provides nulls for event-specific fields (like transaction_id) to allow 
-- for clean unions and standardised frontend data tables.
DROP VIEW IF EXISTS v_metrics_flat;
CREATE VIEW v_metrics_flat AS
SELECT
    m.id AS event_id_internal,
    m.timestamp,
    m.source,
    m.entity_id AS atm_id,
    json_extract(m.payload, '$.correlation_id') AS correlation_id,
    json_extract(m.payload, '$.transaction_id') AS transaction_id,
    NULL AS event_type,
    NULL AS severity,
    NULL AS message,
    COALESCE(json_extract(m.payload, '$.http_status_code'), json_extract(m.payload, '$.atm_status')) AS atm_status,
    m.metric_name,
    m.metric_value,
    NULL AS response_time_ms,
    NULL AS error_code,
    NULL AS exception_class,
    NULL AS error_detail,
    COALESCE(json_extract(m.payload, '$.component'), json_extract(m.payload, '$.service_name'), json_extract(m.payload, '$.resource_type')) AS component,
    m.payload AS raw_payload
FROM metrics m;

-- 8. UNIFIED ANALYSIS VIEW (v_unified_analysis)
-- The master view for the frontend timeline and diagnostic engine.
-- Unions the flattened events and metrics together into a single, time-ordered stream.
-- This fulfills the NFR for 'Extensibility' by allowing the frontend to query exactly
-- one source for the entire ATM timeline (both logs and telemetry).
DROP VIEW IF EXISTS v_unified_analysis;
CREATE VIEW v_unified_analysis AS
-- Events side
SELECT
    event_id_internal,
    timestamp,
    COALESCE(source, json_extract(raw_payload, '$.source'), 'EVENT') AS source,
    COALESCE(atm_id, json_extract(raw_payload, '$.atm_id'), json_extract(raw_payload, '$.entity_id')) AS atm_id,
    correlation_id,
    transaction_id,
    event_type,
    COALESCE(severity, json_extract(raw_payload, '$.log_level'), 'UNKNOWN') AS severity,
    message,
    atm_status,
    component,
    NULL AS metric_name,
    NULL AS metric_value,
    COALESCE(response_time_ms, json_extract(raw_payload, '$.response_time_ms')) AS response_time_ms,
    error_code,
    exception_class,
    error_detail,
    raw_payload
FROM v_events_flat

UNION ALL

-- Metrics side
SELECT
    event_id_internal,
    timestamp,
    COALESCE(source, json_extract(raw_payload, '$.source'), 'METRIC') AS source,
    COALESCE(atm_id, json_extract(raw_payload, '$.atm_id'), json_extract(raw_payload, '$.entity_id')) AS atm_id,
    correlation_id,
    transaction_id,
    event_type,
    COALESCE(severity, json_extract(raw_payload, '$.log_level'), 'UNKNOWN') AS severity,
    message,
    atm_status,
    component,
    metric_name,
    metric_value,
    COALESCE(response_time_ms, json_extract(raw_payload, '$.response_time_ms')) AS response_time_ms,
    error_code,
    exception_class,
    error_detail,
    raw_payload
FROM v_metrics_flat;
