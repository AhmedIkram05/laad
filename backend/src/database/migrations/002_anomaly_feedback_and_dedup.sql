-- Migration: per-user anomaly feedback idempotency + anomaly dedup constraint
--
-- 1) anomaly_feedback: one row per (user, anomaly, feedback_type). The
--    feedback endpoint records each user's rating once, so a repeat DISLIKE
--    no longer re-increments anomalies.false_positive_count.
-- 2) UNIQUE (anomaly_type, atm_id, detected_at) on anomalies closes the
--    consumer double-insert race. Existing duplicates are removed first
--    (lowest id kept) so the constraint can be created on live data.
--
-- Note: the consumer-side INSERT is not made idempotent here; with this
-- constraint a duplicate insert now fails and can be retried/skipped by the
-- consumer's error handling.

CREATE TABLE IF NOT EXISTS anomaly_feedback (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(id),
    anomaly_id BIGINT NOT NULL REFERENCES anomalies(id) ON DELETE CASCADE,
    feedback_type TEXT NOT NULL CHECK (feedback_type IN ('LIKE', 'DISLIKE')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (user_id, anomaly_id, feedback_type)
);

-- Remove duplicate anomaly rows (keep the lowest id per dup group) so the
-- unique constraint below can be applied to existing data.
DELETE FROM anomalies a
USING anomalies b
WHERE a.id > b.id
  AND a.anomaly_type = b.anomaly_type
  AND a.atm_id IS NOT DISTINCT FROM b.atm_id
  AND a.detected_at = b.detected_at;

ALTER TABLE anomalies
    DROP CONSTRAINT IF EXISTS uq_anomalies_type_atm_detected;

ALTER TABLE anomalies
    ADD CONSTRAINT uq_anomalies_type_atm_detected
    UNIQUE (anomaly_type, atm_id, detected_at);
