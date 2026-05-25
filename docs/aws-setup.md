# AWS Setup — MLflow Production Configuration

The MLflow service supports production-grade storage via RDS PostgreSQL + S3.

## Environment Variables

| Env Var | Purpose | Example |
|---|---|---|
| `MLFLOW_BACKEND_STORE_URI` | MLflow tracking backend | `postgresql://user:pass@rds-endpoint:5432/mlflow_db` |
| `MLFLOW_S3_ARTIFACT_ROOT` | S3 artifact bucket | `s3://laad-mlflow-artifacts` |
| `AWS_ACCESS_KEY_ID` | IAM credential for S3 | `AKIA...` |
| `AWS_SECRET_ACCESS_KEY` | IAM credential for S3 | (secret key) |
| `AWS_DEFAULT_REGION` | AWS region | `eu-west-2` |
| `GIT_COMMIT_SHA` | Git SHA injected at runtime | `export GIT_COMMIT_SHA=$(git rev-parse HEAD \| cut -c1-8)` |

## Git SHA: Two Options

**Option A — Auto-inject at runtime (Recommended):**

```bash
export GIT_COMMIT_SHA=$(git rev-parse HEAD | cut -c1-8)
docker compose --profile ml up -d
```

**Option B — Hardcoded in `.env`:**

```env
GIT_COMMIT_SHA=ceecc5c7
```

Both `train.py` and `ml_detector.py` check `os.getenv("GIT_COMMIT_SHA")` first. If empty, they fall back to `git rev-parse HEAD`.

## Testing AWS Connectivity

### Step 1: Test S3 bucket access

```bash
# List bucket
aws s3 ls s3://laad-mlflow-artifacts

# Test write
echo "test" > /tmp/mlflow-test.txt
aws s3 cp /tmp/mlflow-test.txt s3://laad-mlflow-artifacts/test-upload.txt
aws s3 rm s3://laad-mlflow-artifacts/test-upload.txt
```

**If this fails:**

- Verify IAM user has `s3:ListBucket`, `s3:GetObject`, `s3:PutObject`, `s3:DeleteObject`
- Verify bucket policy allows your IAM user/account
- Verify `AWS_DEFAULT_REGION` matches your bucket's region

### Step 2: Test RDS connectivity

```bash
psql "postgresql://db-user:db-password@db-endpoint:5432/db-name" -c "SELECT 1;"
```

**"Connection refused" — debug checklist:**

1. **VPC Security Group Inbound Rules:** Type=PostgreSQL (5432), Source=your IP or `0.0.0.0/0` for testing
2. **VPC Subnet Route Tables:** Subnets must have a route to an Internet Gateway
3. **VPC Network ACLs:** TCP 5432 inbound from your IP, ephemeral ports outbound
4. **RDS "Publicly accessible" flag:** Must be `Yes` (toggle requires reboot)

### Step 3: Verify MLflow with production config

```bash
export GIT_COMMIT_SHA=$(git rev-parse HEAD | cut -c1-8)
docker compose --profile ml up -d mlflow
```

**Verify:**

1. Open `http://localhost:5001`
2. Go to **Experiments** → `atm-anomaly-detection`
3. Go to **Models** → confirm `atm-xgb-classifier` and `atm-isolation-forest`
4. After training, verify S3 artifacts: `aws s3 ls s3://laad-mlflow-artifacts/`

## Docker Configuration

The MLflow Dockerfile (`Dockerfile.mlflow`) adds `psycopg2-binary` (PostgreSQL driver) and `boto3` (AWS SDK) — not included in the official MLflow image.

`docker-compose.yml` passes env vars for the backend store URI and S3 artifact root with defaults falling back to SQLite + Docker volume.

**Note:** Training runs in the `backend` container, not `mlflow`. The `mlflow` container only serves the tracking UI/API. Actual training and artifact uploads happen in `backend`.

## Verified Production Configuration (May 2026)

- RDS PostgreSQL 18.4: `laad-mlflow-postgres.cz6ckmy2u089.eu-west-2.rds.amazonaws.com:5432/mlflow_db`
- S3 Bucket: `s3://laad-mlflow-artifacts` (eu-west-2)
- Artifact uploads, migrations, and security group verified operational
