-- Migration: Rename anomaly detection sources
-- Old values: CLASSIFIER, SIGNAL_CORRELATOR
-- New values: ML_ENSEMBLE, HEURISTIC
-- ZSCORE stays unchanged

-- Update CLASSIFIER -> ML_ENSEMBLE
UPDATE anomalies
SET explanation = (
    jsonb_set(
        explanation::jsonb,
        '{source}',
        '"ML_ENSEMBLE"'::jsonb
    )
)::text
WHERE (explanation::jsonb)->>'source' = 'CLASSIFIER';

-- Update SIGNAL_CORRELATOR -> HEURISTIC
UPDATE anomalies
SET explanation = (
    jsonb_set(
        explanation::jsonb,
        '{source}',
        '"HEURISTIC"'::jsonb
    )
)::text
WHERE (explanation::jsonb)->>'source' = 'SIGNAL_CORRELATOR';

-- Optional: Verify the migration worked
-- SELECT DISTINCT (explanation::jsonb)->>'source' AS detection_source FROM anomalies;
