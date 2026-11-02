-- Migration: Rename anomaly detection sources
-- Old values: CLASSIFIER, SIGNAL_CORRELATOR
-- New values: ML_ENSEMBLE, HEURISTIC
-- ZSCORE stays unchanged
--
-- Migrations are applied manually, so the batching below only matters when
-- the anomalies table is already large: both renames rewrite every matching
-- row. Each source is renamed in batches of 5000 inside one explicit
-- transaction, so an interrupted run rolls back instead of leaving the table
-- half-renamed.

BEGIN;

DO $$
DECLARE
    batch_size CONSTANT int := 5000;
    affected int;
    rename_rec RECORD;
BEGIN
    FOR rename_rec IN
        SELECT * FROM (VALUES
            ('CLASSIFIER', 'ML_ENSEMBLE'),
            ('SIGNAL_CORRELATOR', 'HEURISTIC')
        ) AS v(old_source, new_source)
    LOOP
        LOOP
            UPDATE anomalies
            SET explanation = jsonb_set(
                explanation::jsonb,
                '{source}',
                to_jsonb(rename_rec.new_source)
            )::text
            WHERE id IN (
                SELECT id
                FROM anomalies
                WHERE (explanation::jsonb)->>'source' = rename_rec.old_source
                ORDER BY id
                LIMIT batch_size
            );
            GET DIAGNOSTICS affected = ROW_COUNT;
            EXIT WHEN affected = 0;
        END LOOP;
    END LOOP;
END $$;

COMMIT;
