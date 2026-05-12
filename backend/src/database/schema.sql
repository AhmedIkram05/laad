-- PostgreSQL schema for LAAD — events, metrics, anomalies, users, ingestion_errors

-- 1. atms
CREATE TABLE IF NOT EXISTS atms (
    atm_id TEXT PRIMARY KEY,
    os_version TEXT,
    location_code TEXT
);

-- 2. events
CREATE TABLE IF NOT EXISTS events (
    id BIGSERIAL PRIMARY KEY,
    timestamp TIMESTAMPTZ NOT NULL,
    source TEXT NOT NULL,
    atm_id TEXT,
    correlation_id TEXT,
    transaction_id TEXT,
    event_type TEXT,
    severity TEXT,
    message TEXT,
    payload JSONB
);

-- 3. metrics
CREATE TABLE IF NOT EXISTS metrics (
    id BIGSERIAL PRIMARY KEY,
    timestamp TIMESTAMPTZ NOT NULL,
    source TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    metric_name TEXT NOT NULL,
    metric_value DOUBLE PRECISION NOT NULL,
    payload JSONB
);

-- 4. anomalies
CREATE TABLE IF NOT EXISTS anomalies (
    id BIGSERIAL PRIMARY KEY,
    detected_at TIMESTAMPTZ NOT NULL,
    anomaly_type TEXT NOT NULL,
    atm_id TEXT REFERENCES atms(atm_id),
    correlation_id TEXT,
    transaction_id TEXT,
    model_confidence_score DOUBLE PRECISION,
    severity TEXT NOT NULL,
    title TEXT NOT NULL,
    explanation TEXT NOT NULL,
    recommended_action TEXT,
    sources_involved JSONB,
    feedback_rating TEXT,
    is_active INTEGER DEFAULT 1,
    is_starred INTEGER DEFAULT 0
);

-- 5. ingestion_errors
CREATE TABLE IF NOT EXISTS ingestion_errors (
    id BIGSERIAL PRIMARY KEY,
    timestamp TIMESTAMPTZ NOT NULL,
    source TEXT NOT NULL,
    error_detail TEXT NOT NULL,
    raw_input TEXT
);

-- 6. users
CREATE TABLE IF NOT EXISTS users (
    id BIGSERIAL PRIMARY KEY,
    username TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'user' CHECK (role IN ('admin', 'user')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 7. retention_config
CREATE TABLE IF NOT EXISTS retention_config (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    retention_days INTEGER NOT NULL DEFAULT 7,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_users_username ON users(username);
CREATE INDEX IF NOT EXISTS idx_events_correlation ON events(correlation_id);
CREATE INDEX IF NOT EXISTS idx_events_atm_time ON events(atm_id, timestamp);
CREATE INDEX IF NOT EXISTS idx_events_transaction ON events(transaction_id);
CREATE INDEX IF NOT EXISTS idx_events_source ON events(source);
CREATE INDEX IF NOT EXISTS idx_metrics_entity_time ON metrics(entity_id, timestamp);
CREATE INDEX IF NOT EXISTS idx_metrics_name_time ON metrics(metric_name, timestamp);
CREATE INDEX IF NOT EXISTS idx_metrics_source ON metrics(source);
CREATE INDEX IF NOT EXISTS idx_anomalies_atm ON anomalies(atm_id);
CREATE INDEX IF NOT EXISTS idx_anomalies_active_time ON anomalies(is_active, detected_at);
CREATE INDEX IF NOT EXISTS idx_anomalies_correlation ON anomalies(correlation_id);
CREATE INDEX IF NOT EXISTS idx_anomalies_type_time ON anomalies(anomaly_type, detected_at);

-- Views
DROP VIEW IF EXISTS v_unified_analysis;
DROP VIEW IF EXISTS v_metrics_flat;
DROP VIEW IF EXISTS v_events_flat;
CREATE VIEW v_events_flat AS
SELECT
    e.id AS event_id_internal,
    e.timestamp,
    e.source,
    e.atm_id,
    COALESCE(e.correlation_id, e.payload->>'correlation_id', e.payload->>'trace_id') AS correlation_id,
    e.transaction_id,
    e.event_type,
    e.severity,
    e.message,
    e.payload->>'location_code' AS location_code,
    (e.payload->>'response_time_ms')::NUMERIC AS response_time_ms,
    COALESCE(e.payload->>'error_code', e.payload->>'transaction_failure_reason') AS error_code,
    e.payload->>'exception_class' AS exception_class,
    COALESCE(e.payload->>'error_detail', e.payload->>'exception_message') AS error_detail,
    COALESCE(e.payload->>'component', e.payload->>'service_name', e.payload->>'sensor_type') AS component,
    COALESCE(e.payload->>'http_status_code', e.payload->>'atm_status') AS atm_status,
    e.payload AS raw_payload
FROM events e;

CREATE VIEW v_metrics_flat AS
SELECT
    m.id AS event_id_internal,
    m.timestamp,
    m.source,
    m.entity_id AS atm_id,
    m.payload->>'correlation_id' AS correlation_id,
    m.payload->>'transaction_id' AS transaction_id,
    NULL::TEXT AS event_type,
    NULL::TEXT AS severity,
    NULL::TEXT AS message,
    COALESCE(m.payload->>'http_status_code', m.payload->>'atm_status') AS atm_status,
    m.metric_name,
    m.metric_value,
    NULL::NUMERIC AS response_time_ms,
    NULL::TEXT AS error_code,
    NULL::TEXT AS exception_class,
    NULL::TEXT AS error_detail,
    COALESCE(m.payload->>'component', m.payload->>'service_name', m.payload->>'resource_type') AS component,
    m.payload AS raw_payload
FROM metrics m;

CREATE VIEW v_unified_analysis AS
SELECT
    event_id_internal, timestamp,
    COALESCE(source, raw_payload->>'source', 'EVENT') AS source,
    COALESCE(atm_id, raw_payload->>'atm_id', raw_payload->>'entity_id') AS atm_id,
    correlation_id, transaction_id, event_type,
    COALESCE(severity, raw_payload->>'log_level', 'UNKNOWN') AS severity,
    message, atm_status, component,
    NULL::TEXT AS metric_name, NULL::DOUBLE PRECISION AS metric_value,
    response_time_ms, error_code, exception_class, error_detail,
    raw_payload
FROM v_events_flat
UNION ALL
SELECT
    event_id_internal, timestamp,
    COALESCE(source, raw_payload->>'source', 'METRIC') AS source,
    COALESCE(atm_id, raw_payload->>'atm_id', raw_payload->>'entity_id') AS atm_id,
    correlation_id, transaction_id, event_type,
    COALESCE(severity, raw_payload->>'log_level', 'UNKNOWN') AS severity,
    message, atm_status, component,
    metric_name, metric_value,
    response_time_ms, error_code, exception_class, error_detail,
    raw_payload
FROM v_metrics_flat;
