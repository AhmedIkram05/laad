# Architecture Fixes

## Scaler fitted on full 49 features (not 46-dim subset)

The `StandardScaler` was previously fitted after feature selection, resulting in a 46-dim scaler. At inference time, `scaler.transform` received 49-dim features, causing `ValueError: X has 49 features, but StandardScaler is expecting 46 features`.

**Fix:** Fitted scaler on ALL 49 `X_normal` features before applying feature selection subset — both training and inference now scale first, then subset. (`train.py:351`)

## XGBoost receives full 49-dim features (separate from IF path)

Feature selection (49→46) was applied to a shared `features` variable used by both Isolation Forest and XGBoost. Since XGBoost was trained on all 49 features, `predict_proba` raised `ValueError: Feature shape mismatch, expected: 49, got 46`.

**Fix:** Maintained two independent paths: `features_scaled` (49-dim, for XGBoost) and `features_if` (46-dim after subset, for IF). (`ml_detector.py:508-527`)

## Git SHA = "unknown" in Docker

`git rev-parse HEAD` fails inside containers without `.git` folder. Fixed by checking `GIT_COMMIT_SHA` env var first in `train.py:173-179` and `ml_detector.py:204-212`.

## Duplicate model versions per training

`log_model(registered_model_name=)` created version N, then explicit `mlflow.register_model()` created N+1. Fixed by removing `registered_model_name=` param; only the explicit `register_model()` call creates versions now. (`train.py:415-416`)

## Local-only storage (not production-ready)

SQLite backend + Docker volume artifact root. Fixed by: (1) New `Dockerfile.mlflow` adding `psycopg2-binary` and `boto3`, (2) Env var interpolation for backend store URI and artifact root in `docker-compose.yml`, (3) AWS credentials passed through to `backend` container for training artifact uploads.
