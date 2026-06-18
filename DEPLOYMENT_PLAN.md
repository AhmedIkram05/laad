# LAAD AWS Deployment Plan

## Overview

Deploy the LAAD platform to AWS with Terraform-managed infrastructure and GitHub Actions CI/CD. Three high-ROI items:

1. **ECS Fargate** — FastAPI backend + Kafka consumer as separate services behind ALB
2. **SageMaker real-time endpoint** — XGBoost champion model from MLflow registry
3. **Infrastructure-as-Code** — Terraform with S3 + DynamoDB state backend

## Prerequisites (Manual)

Before starting implementation, ensure these manual steps are completed:

1. **AWS CLI credentials**: Ensure `aws configure` is set with an IAM user/role that has `AdministratorAccess` (or equivalent) for the account. The OIDC role we create via Terraform will supersede this for CI/CD, but Terraform bootstrap needs creds initially.

2. **Verify existing resources**. Confirm these exist in `eu-west-2`:
   - RDS PostgreSQL instance: `laad-mlflow-postgres` (from .env)
   - S3 bucket: `laad-mlflow-artifacts`
   - The MLflow tracking URI: `postgresql://mlflow_admin:laadmlflow@laad-mlflow-postgres.cz6ckmy2u089.eu-west-2.rds.amazonaws.com:5432/mlflow_db`

3. **Install Terraform**: `brew install terraform` (macOS)

4. **GitHub OIDC setup**: The Terraform bootstrap needs initial AWS creds (step 1). After Terraform creates the OIDC provider + IAM role, you configure GitHub as described below.

## Environment Variables & Secrets Inventory

The following secrets must exist in AWS Secrets Manager (created by Terraform):

| Secret Name | Key | Source |
|---|---|---|
| `laad/db/master` | All RDS connection params for LAAD app RDS | Terraform-generated |
| `laad/db/mlflow` | MLflow RDS connection params | From existing .env |
| `laad/app/jwt` | `JWT_SECRET_KEY` | Generate: `python -c \"import secrets; print(secrets.token_hex(32))\"` |
| `laad/rag/ollama` | `OLLAMA_API_KEY`, `OPENROUTER_API_KEY` | From existing .env |
| `laad/app/backend` | All runtime env vars | Compiled from docker-compose.yml + .env |
| `laad/sagemaker` | `SAGEMAKER_ENDPOINT_NAME`, `SAGEMAKER_REGION` | Created by Terraform |
| `laad/mlflow` | `MLFLOW_TRACKING_URI`, `MLFLOW_S3_ARTIFACT_ROOT`, AWS creds | From existing .env |

## Region

All resources deploy to **eu-west-2** to match the existing MLflow RDS + S3 bucket.

## Architecture

```
[GitHub Actions] ──OIDC──> [AWS IAM Role]
       |
       ├── terraform apply ──> [S3 backend + DynamoDB lock]
       ├── build & push ──> [ECR]
       └── deploy ──> [ECS Fargate]

Internet ──> ALB (HTTPS, ACM self-signed) ──> ECS Fargate (FastAPI)
                                                  |
                     [Local Docker Kafka <──> Local Consumer] (dev only, not deployed)
                                                  |
                     [ECS Fargate API] ──> [SageMaker endpoint (XGBoost)]
                                                  |
                     [ECS Fargate API] ──> [RDS PostgreSQL (new, LAAD app)]
                                                  |
                     [ECS Fargate API + Consumer] ──> [RDS PostgreSQL (existing, MLflow)]

[CloudFront CDN] <── [S3 Bucket (React static build)] <── CI/CD build
```

## Terraform Module Structure

```
terraform/
├── main.tf                    # Provider config, state backend, modules
├── variables.tf               # All input variables (region, env, existing RDS ID, etc.)
├── outputs.tf                 # ALB DNS, ECR repos, SageMaker endpoint name
├── backend.tf                 # S3 + DynamoDB state backend config
├── providers.tf               # AWS provider config, OIDC provider
│
├── modules/
│   ├── vpc/
│   │   ├── main.tf            # VPC, 2 public + 2 private subnets, NAT Gateway, IGW, route tables
│   │   ├── variables.tf
│   │   └── outputs.tf         # vpc_id, public_subnet_ids, private_subnet_ids, nat_gateway_id
│   │
│   ├── ecs/
│   │   ├── main.tf            # ECS cluster (Fargate), task definitions, services, ALB, TG, SG
│   │   ├── variables.tf
│   │   ├── outputs.tf         # alb_dns, cluster_arn, service_names
│   │   └── task_definitions/
│   │       ├── api.json.tpl       # FastAPI task definition template
│   │       └── consumer.json.tpl  # Kafka consumer task definition template
│   │
│   ├── sagemaker/
│   │   ├── main.tf            # SageMaker model, endpoint config, endpoint (real-time provisioned)
│   │   ├── variables.tf
│   │   └── outputs.tf         # endpoint_name, endpoint_arn
│   │
│   ├── iam/
│   │   ├── main.tf            # ECS task roles, SageMaker execution role, GitHub OIDC role
│   │   ├── variables.tf
│   │   └── outputs.tf         # ecs_task_role_arn, sagemaker_role_arn, github_actions_role_arn
│   │
│   ├── ecr/
│   │   ├── main.tf            # ECR repos for backend, kafka-consumer
│   │   ├── variables.tf
│   │   └── outputs.tf         # repo_urls
│   │
│   ├── rds/
│   │   ├── main.tf            # New RDS PostgreSQL 16 for LAAD app data (anomalies, events, users)
│   │   ├── variables.tf
│   │   └── outputs.tf         # endpoint, port, db_name, security_group_id
│   │
│   ├── secrets/
│   │   ├── main.tf            # All Secrets Manager entries
│   │   ├── variables.tf
│   │   └── outputs.tf         # secret_arns
│   │
│   ├── frontend/
│   │   ├── main.tf            # S3 bucket + CloudFront distribution for React static build
│   │   ├── variables.tf
│   │   └── outputs.tf         # cloudfront_domain, s3_bucket_name
│   │
│   └── security/
│       ├── main.tf            # Security groups for ALB, ECS tasks, RDS, SageMaker VPC config
│       ├── variables.tf
│       └── outputs.tf
│
├── environments/
│   └── prod/
│       ├── terraform.tfvars   # Production-specific variable values
│       └── provider.tf
│
    └── bootstrap/
        └── main.tf            # One-time script to create S3 bucket + DynamoDB table for state

## Terraform Module Details

### Bootstrap (one-time manual)

```hcl
# terraform/bootstrap/main.tf
# Run once: terraform apply -auto-approve
resource "aws_s3_bucket" "tf_state" {
  bucket = "laad-terraform-state-<unique-suffix>"
  # e.g. "laad-terraform-state-abc123"
}

resource "aws_s3_bucket_versioning" "tf_state" {
  bucket = aws_s3_bucket.tf_state.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "tf_state" {
  bucket = aws_s3_bucket.tf_state.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_dynamodb_table" "tf_lock" {
  name         = "laad-terraform-lock"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "LockID"
  attribute {
    name = "LockID"
    type = "S"
  }
}
```

**Manual step:** Choose a unique suffix (e.g. your initials + random word). Run from `terraform/bootstrap/`. After creation, the S3 bucket name and DynamoDB table name are used in `backend.tf`.

### VPC Module

Creates a VPC with:
- **2 availability zones** (eu-west-2a, eu-west-2b) — sufficient for a portfolio project, reduces NAT Gateway cost
- **2 public subnets** — for ALB
- **2 private subnets** — for ECS Fargate tasks (API + consumer) and SageMaker VPC
- **1 NAT Gateway** in public subnet (single-AZ to save cost; the other AZ routes through the same NAT)
- **Internet Gateway** — for public subnets
- **Route tables** — public (IGW), private (NAT)
- **VPC Endpoints** for S3 and DynamoDB (gateway endpoints, no extra cost) — so ECS tasks can pull from ECR and push logs to CloudWatch without NAT

Key decisions:
- Single NAT Gateway saves ~$35/mo vs multi-AZ
- Only 2 AZs for portfolio-level HA
- VPC CIDR: `10.0.0.0/16` (non-overlapping with existing MLflow RDS VPC — **must verify**)

### RDS Module

Creates a new RDS PostgreSQL 16 instance for the LAAD application data (not MLflow — that's a separate existing RDS).

Resources:

1. **`aws_db_subnet_group`** — Places the RDS in the VPC's private subnets (2 AZs)

2. **`aws_db_instance`** (`laad-postgres`):
   - `engine = "postgres"`, `engine_version = "16"`
   - `instance_class = "db.t4g.micro"` — cheapest, ~$15/mo, burstable
   - `allocated_storage = 20` GB (gp3)
   - `db_name = "atm_platform"`, `username = "atm_user"`
   - `password` — randomly generated, stored in Secrets Manager
   - `db_subnet_group_name` — points to private subnets
   - `vpc_security_group_ids` — RDS SG (allows PostgreSQL from ECS API + Consumer SGs)
   - `skip_final_snapshot = true` (portfolio project — snapshots add cost)
   - `backup_retention_period = 7` (basic backup for learning)
   - `deletion_protection = false` (can destroy for cleanup)
   - `storage_encrypted = true` (SSE-S3 at rest)

3. **`aws_secretsmanager_secret_version`** — Stores the RDS credentials in `laad/db/master`:
   ```json
   {
     "POSTGRES_HOST": "<rds-endpoint>",
     "POSTGRES_PORT": "5432",
     "POSTGRES_DB": "atm_platform",
     "POSTGRES_USER": "atm_user",
     "POSTGRES_PASSWORD": "<random-password>"
   }
   ```

**Important:** The RDS security group must allow ingress on port 5432 from:
- ECS API security group
- ECS Consumer security group (if deployed)
- The existing MLflow RDS security group is separate — we do NOT modify it

**Schema setup:** After RDS creation, the schema must be applied. This is done via a one-time `init_db()` call in the CI/CD deploy workflow (see Phase 6).

### IAM Module

Creates the following IAM roles with least-privilege policies:

1. **GitHub Actions OIDC role** (`laad-github-actions-role`):
   - Trust policy allowing `repo:ahmedikram/laad` (your repo) from GitHub's OIDC issuer
   - Attached policies: `AmazonEC2ContainerRegistryPowerUser`, `AmazonECS_FullAccess`, `IAMReadOnlyAccess`, custom policy for SageMaker deploy permissions
   - Used by CI/CD to: push to ECR, update ECS services, deploy SageMaker endpoint

2. **ECS Task Execution Role** (`laad-ecs-execution-role`):
   - `AmazonECSTaskExecutionRolePolicy` (for ECR pull + CloudWatch logs)
   - Custom policy for Secrets Manager read (`laad/*`)

3. **ECS Task Role** (`laad-ecs-task-role`):
   - Custom policy: `sagemaker:InvokeEndpoint` on the specific endpoint ARN
   - Custom policy: RDS access (based on security group, not IAM for Postgres)
   - Custom policy: CloudWatch logs (CreateLogStream, PutLogEvents)
   - Custom policy: S3 read on `laad-mlflow-artifacts` (for model artifacts if needed)

4. **SageMaker Execution Role** (`laad-sagemaker-execution-role`):
   - `AmazonSageMakerFullAccess` (or scoped-down equivalent)
   - Custom policy: S3 read on `laad-mlflow-artifacts` (to load model artifacts)
   - Custom policy: ECR pull (for the XGBoost inference container)

### Secrets Module

Creates the following Secrets Manager entries. Deploy scripts read these at ECS task startup.

1. **`laad/db/master`** — Auto-generated random password (30 chars, no special chars to avoid URL encoding issues). RDS master credentials for the *new* project database (not MLflow).

2. **`laad/app/jwt`** — Store `JWT_SECRET_KEY`. User must generate and set this post-deploy.

3. **`laad/rag/ollama`** — JSON blob:
   ```json
   {
     "OLLAMA_API_KEY": "<from .env>",
     "OPENROUTER_API_KEY": "<from .env>"
   }
   ```

4. **`laad/mlflow`** — JSON blob:
   ```json
   {
     "MLFLOW_TRACKING_URI": "postgresql://mlflow_admin:laadmlflow@laad-mlflow-postgres.cz6ckmy2u089.eu-west-2.rds.amazonaws.com:5432/mlflow_db",
     "MLFLOW_S3_ARTIFACT_ROOT": "s3://laad-mlflow-artifacts",
     "AWS_ACCESS_KEY_ID": "<from .env>",
     "AWS_SECRET_ACCESS_KEY": "<from .env>",
     "AWS_DEFAULT_REGION": "eu-west-2"
   }
   ```

5. **`laad/app/backend`** — JSON blob with all remaining env vars (REDIS_HOST, REDIS_PORT, CHROMA_HOST, CHROMA_PORT, RAG_* settings, etc. — defaults from docker-compose.yml).

### ECR Module

Creates two ECR repositories:
- `laad-backend` — For the FastAPI Docker image
- `laad-consumer` — For the Kafka consumer Docker image (same base image, different CMD; could share a single repo with separate tags)

Both repositories have `image_scanning_configuration = { scan_on_push = true }` and `lifecycle_policy` to keep only the last 10 images.

### ECS Module

#### Cluster

- `aws_ecs_cluster` named `laad-cluster` (Fargate capacity provider, no EC2)
- `aws_ecs_cluster_capacity_providers` — uses `FARGATE` and `FARGATE_SPOT`

#### Task Definitions

**API Task Definition** (`laad-api`):
- **CPU/Memory**: 1024 CPU / 3072 MB (sufficient for FastAPI + LLM/embedding calls)
- **Container image**: `laad-backend:latest` (from ECR)
- **Port mappings**: 8000
- **Secrets**: All secrets from Secrets Manager injected as environment variables
- **Log group**: `/ecs/laad-api` with 30-day retention
- **Health check**: CMD `python -c 'import urllib.request; urllib.request.urlopen("http://localhost:8000/docs")'` — same as docker-compose
- **Environment variables** (from secrets + plaintext for non-sensitive):
  - `POSTGRES_HOST`, `POSTGRES_PORT`, `POSTGRES_DB`, `POSTGRES_USER` — from Secrets Manager
  - `JWT_SECRET_KEY` — from Secrets Manager
  - `MLFLOW_TRACKING_URI`, `MLFLOW_S3_ARTIFACT_ROOT`, `AWS_*` — from Secrets Manager
  - `REDIS_HOST=redis`, `REDIS_PORT=6379` — these remain as local Docker services, **or** see below for Redis option
  - `CHROMA_HOST=chromadb`, `CHROMA_PORT=8000` — local Docker
  - `OLLAMA_API_KEY`, `OPENROUTER_API_KEY` — from Secrets Manager (RAG calls Ollama cloud API, no local Ollama needed)
  - `RAG_PRIMARY_MODEL`, `RAG_FALLBACK_MODEL`, `RAG_TOP_K`, etc. — defaults from docker-compose
  - `SAGEMAKER_ENDPOINT_NAME` — from Secrets Manager
  - `OLLAMA_BASE_URL=https://ollama.com` — cloud API, not local
- **Command**: `python -m uvicorn backend.src.api.server:app --host 0.0.0.0 --port 8000 --workers 4` (same as Dockerfile but with explicit workers)
- **Storage**: 21 GB ephemeral storage (default for Fargate)

**Consumer Task Definition** (`laad-consumer`):
- **CPU/Memory**: 512 CPU / 1024 MB (lightweight)
- **Container image**: `laad-consumer:latest` (or `laad-backend:latest` with different CMD)
- **Command**: `python -m backend.kafka.consumer`
- **Secrets**: Same DB creds as API, MLflow config
- **Environment**: Same as docker-compose kafka-consumer section
- **Log group**: `/ecs/laad-consumer`

#### ALB

- `aws_lb` — Application Load Balancer, internet-facing, dual-stack
- `aws_lb_target_group` — HTTP:8000, health check path `/docs` (FastAPI auto-docs)
- `aws_lb_listener` — **HTTPS:443** with self-signed ACM cert (no domain), redirect HTTP:80 → HTTPS:443
- Security group: allows 443 from 0.0.0.0/0, allows 80 from 0.0.0.0/0 (redirect)

#### Service

**API Service** (`laad-api-service`):
- 1 desired task (scale down when not in use)
- FARGATE_SPOT capacity provider (50-90% savings)
- Attached to ALB target group
- Service discovery: optional
- Deployment: rolling update (minimum 0 healthy tasks during deploy — portfolio project, no need for zero-downtime)

**Consumer Service** (`laad-consumer-service`):
- 1 desired task
- FARGATE_Spot, no ALB
- No trigger from ALB

#### CloudWatch Logs

- Log group `/ecs/laad-api` with 14-day retention (portfolio, not production)
- Log group `/ecs/laad-consumer` with 14-day retention
- Metric filter: `5xx errors` → CloudWatch alarm
- Metric filter: `CRITICAL` in logs → CloudWatch alarm

### Frontend Module

Creates the infrastructure for serving the React frontend. The frontend is a static single-page application (no SSR).

Resources:

1. **`aws_s3_bucket`** (`laad-frontend`):
   - `bucket = "laad-frontend-<unique-suffix>"` (S3 bucket names must be globally unique)
   - `acl = "private"` (CloudFront is the only access point)
   - `website = null` (no direct S3 website hosting — enforced through CloudFront OAC)
   - Block all public access (default)

2. **`aws_s3_bucket_public_access_block`** — Blocks all public access
3. **`aws_s3_bucket_versioning`** — Optional (for CI/CD rollback. Can skip to save costs.)

4. **`aws_cloudfront_distribution`**:
   - `origin` — S3 bucket via Origin Access Control (OAC)
   - `default_cache_behavior`:
     - `forward = "none"` (static SPA has no dynamic routing from CloudFront)
     - `viewer_protocol_policy = "redirect-to-https"`
     - `allowed_methods = ["GET", "HEAD", "OPTIONS"]`
     - `cached_methods = ["GET", "HEAD"]`
     - `default_ttl = 3600`
     - `max_ttl = 86400`
   - `custom_error_response` — 404 → index.html (SPA routing)
   - `price_class = "PriceClass_100"` (only US + Europe — cheapest, we're in eu-west-2)
   - `enabled = true`
   - `default_root_object = "index.html"`

5. **`aws_cloudfront_origin_access_control`** — OAC for CloudFront → S3 (more secure than OAI)

6. **`aws_s3_bucket_policy`** — Grants read access only to CloudFront (via OAC)

Cost: CloudFront at PriceClass_100 is ~$0.085/GB for data transfer + $0.01/10K requests. For a portfolio project, this is under $1/mo.

### SageMaker Module

Creates a SageMaker real-time endpoint for the XGBoost champion model.

**Architecture note:** The SageMaker endpoint does NOT live in the VPC (public endpoint is simpler for a portfolio project). If VPC-only is desired, it requires `aws_sagemaker_notebook_instance` VPC config, which adds complexity. The default is a public SageMaker endpoint accessed via internet from ECS tasks (which have NAT Gateway).

Resources:
1. **`aws_sagemaker_model`** — Points to the MLflow-registered model artifact in S3:
   - `model_name = "laad-xgb-champion"`
   - `primary_container`:
     - `image` — XGBoost inference container from ECR (`246618743249.dkr.ecr.eu-west-2.amazonaws.com/sagemaker-xgboost:latest` — the official AWS XGBoost serving image)
     - `model_data_url` — `s3://laad-mlflow-artifacts/<path-to-xgb-model>` (requires downloading model from MLflow registry to S3 — see "Manual Steps" below)
   - `execution_role_arn` — SageMaker execution role from IAM module

2. **`aws_sagemaker_endpoint_configuration`**:
   - `production_variants`:
     - `instance_type = "ml.m5.large"` — smallest CPU instance, ~$0.115/hr
     - `initial_instance_count = 1`
     - `initial_variant_weight = 1`
     - `variant_name = "champion"`

3. **`aws_sagemaker_endpoint`**:
   - `endpoint_config_name` — ref to above
   - `name = "laad-xgb-champion"`

**Cost**: ml.m5.large at 730 hours/mo = ~$84/mo. For a portfolio project, you should:
- Stop the endpoint when not in use: `aws sagemaker delete-endpoint --endpoint-name laad-xgb-champion`
- Start when needed: `aws sagemaker create-endpoint ...`
- Or: Set up a CloudWatch Events rule to stop at 8pm, start at 8am weekdays
- The Terraform should include an `aws_sagemaker_endpoint` resource that can be `terraform destroy`'d when not needed

**Important — model data URL manual step**: You must download the champion XGBoost model from MLflow and upload it to the S3 bucket `laad-mlflow-artifacts`. See "Manual Steps" section.

## CI/CD Pipeline Architecture

### Workflow Dependency Graph

```
push to main
    │
    ├── ci.yml (always runs)
    │   ├── Checkout
    │   ├── Lint (backend + frontend)
    │   ├── Backend tests (pytest via Docker)
    │   ├── Frontend tests (vitest)
    │   │
    │   └── ✅ All pass
    │
    └── cd.yml (runs after CI passes, only on main)
        ├── Build & push API Docker image
        │   └── backend/Dockerfile → ECR (laad-backend:latest)
        │
        ├── Build frontend static assets
        │   ├── npm run build (frontend/)
        │   └── Sync dist/ → S3 (laad-frontend-*)
        │
        ├── Deploy API to ECS
        │   └── Force new deployment of laad-api-service
        │
        ├── Invalidate CloudFront cache
        │   └── CreateCloudFrontInvalidation for /* (on S3 bucket)
        │
        └── Notify (Slack or email via SNS)
```

### terraform.yml — Separate Workflow

This workflow is for infrastructure changes only:
- Triggered on PRs that modify `terraform/*`
- Runs `terraform plan`
- On merge to main: `terraform apply`

### API Endpoints Rearchitecture for SageMaker

The backend currently loads models locally via joblib (`ml_detector.py:230-254`). After SageMaker deployment:

1. Add a new environment variable: `SAGEMAKER_ENDPOINT_NAME` (from Secrets Manager)
2. In `ml_detector.py`, add a fallback chain:
   - If `SAGEMAKER_ENDPOINT_NAME` is set → invoke SageMaker endpoint via boto3
   - If SageMaker unavailable (timeout, endpoint stopped) → fall back to local joblib model
   - If neither → run heuristic + Z-score only (current behavior)

This keeps the system resilient during development (local Docker) while enabling SageMaker in production.

### Kafka Consumer on ECS

The consumer needs to reach a Kafka broker. In production, Kafka remains local (Docker), so:
- **ECS consumer cannot reach localhost Kafka.**
- Two options:
  A. **Run Kafka locally, expose via ngrok/tailscale** — not production-grade but works for demo
  B. **Run Kafka on an EC2 instance in the VPC** — adds ~$8/mo for t4g.nano
  C. **Keep consumer running locally on your machine** — simplest, just run `docker compose up kafka-consumer`

**Recommendation: Option C.** Keep the consumer local. Deploy only the API to ECS. The CV story is still strong: "Containerised FastAPI backend deployed to ECS Fargate behind ALB with CI/CD." The consumer being local is an implementation detail. You can still demonstrate the Kafka consumer code in interviews.

If you want a fully cloud-native story, Option B (EC2 t4g.nano for Kafka, Consumer as separate ECS task) adds ~$10/mo to the bill.

## Manual Steps (Required After Terraform Deploy)

These steps cannot be automated and must be performed by you.

### Step 1: Download Champion XGBoost Model from MLflow to S3

The SageMaker endpoint needs the model artifact accessible in S3. MLflow stores it in `s3://laad-mlflow-artifacts/<experiment-id>/<run-id>/artifacts/xgb_classifier/`. You need to:

1. Find the champion model version:
```bash
# Find the registered model version with "champion" alias
aws sagemaker-runtime --region eu-west-2 \
  --output text describe-endpoint-config --endpoint-config-name laad-xgb-champion
```
If not yet deployed, use MLflow CLI:
```bash
# Or via MLflow API
python -c "
import mlflow
client = mlflow.tracking.MlflowClient()
client.set_tracking_uri('postgresql://mlflow_admin:laadmlflow@laad-mlflow-postgres.cz6ckmy2u089.eu-west-2.rds.amazonaws.com:5432/mlflow_db')
mv = client.get_model_version_by_alias('atm-xgb-classifier', 'champion')
print(f'Version: {mv.version}, Run ID: {mv.run_id}')
"
```

2. Download the model artifact to your local machine:
```bash
python -c "
import mlflow
client = mlflow.tracking.MlflowClient()
client.set_tracking_uri('postgresql://mlflow_admin:laadmlflow@laad-mlflow-postgres.cz6ckmy2u089.eu-west-2.rds.amazonaws.com:5432/mlflow_db')
# Download artifact to local dir
client.download_artifacts(run_id='<run-id>', path='xgb_classifier', dst_path='./tmp/')
"
```

3. Upload to a known S3 path for SageMaker:
```bash
# Create the SageMaker model directory
aws s3 cp ./tmp/xgb_classifier \
  s3://laad-mlflow-artifacts/sagemaker-models/xgb-champion/ --recursive
```

4. Note the S3 URI for Terraform: `s3://laad-mlflow-artifacts/sagemaker-models/xgb-champion/`

### Step 2: Set JWT Secret in Secrets Manager

After Terraform creates the secrets (with placeholder values), update `laad/app/jwt`:
```bash
JWT_KEY=$(python -c "import secrets; print(secrets.token_hex(32))")
aws secretsmanager put-secret-value \
  --secret-id laad/app/jwt \
  --secret-string "{\"JWT_SECRET_KEY\": \"$JWT_KEY\"}"
```

### Step 3: Verify ALB Security

After Terraform creates the ALB (with self-signed ACM cert), verify HTTPS works:
```bash
ALB_DNS=$(terraform output -raw alb_dns)
curl -k https://$ALB_DNS/docs
# -k flag bypasses self-signed cert warning
```

### Step 4: Set GitHub Actions OIDC Variables

After Terraform creates the OIDC IAM role, get the role ARN and add it to GitHub:
```bash
GITHUB_ROLE_ARN=$(terraform output -raw github_actions_role_arn)
echo $GITHUB_ROLE_ARN
# Go to: https://github.com/ahmedikram/laad/settings/secrets/actions
# Add: AWS_ROLE_ARN = <output>
# Add: AWS_REGION = eu-west-2
```

### Step 5: (Optional) Kafka Consumer on EC2

If you choose Option B (Kafka on EC2 for cloud-native consumer):
1. The Terraform plan can include an `aws_instance` module (t4g.nano, Amazon Linux 2023)
2. After deploy, SSH in and install Kafka:
```bash
ssh -i <key> ec2-user@<instance-ip>
sudo yum install -y java-11-amazon-corretto-headless
wget https://downloads.apache.org/kafka/3.6.0/kafka_2.13-3.6.0.tgz
tar -xzf kafka_2.13-3.6.0.tgz
# Start KRaft mode (single broker, same as current docker-compose)
cd kafka_2.13-3.6.0
KAFKA_CLUSTER_ID=$(bin/kafka-storage.sh random-uuid)
bin/kafka-storage.sh format -t $KAFKA_CLUSTER_ID -c config/kraft/server.properties
bin/kafka-server-start.sh config/kraft/server.properties &
```

## Implementation Order (for the Implementation Agent)

The implementation agent should execute in this exact order. Each step depends on previous steps.

### Phase 1: Bootstrap & VPC (Agent)

1. Create `terraform/bootstrap/main.tf`
2. Create `terraform/providers.tf` with AWS provider config
3. Create `terraform/variables.tf` with all input variables
4. Create `terraform/backend.tf` with S3 + DynamoDB config
5. Execute: `terraform init` and `terraform apply` from bootstrap
6. Create VPC module with:
   - VPC (10.0.0.0/16), 2 AZs (eu-west-2a, eu-west-2b)
   - 2 public subnets, 2 private subnets
   - Internet Gateway, NAT Gateway (single, in AZ-a)
   - Route tables (public → IGW, private → NAT)
   - Gateway endpoints (S3, DynamoDB)

### Phase 2: RDS (Agent)

1. Create RDS module with:
   - `db.t4g.micro` PostgreSQL 16 in private subnets (2 AZs)
   - Auto-generated password stored in Secrets Manager as `laad/db/master`
   - RDS security group: allow port 5432 from ECS API SG
   - 20 GB gp3, backup retention 7 days, storage encrypted
   - Output: endpoint, port, db_name, RDS SG ID
   - **Note**: Schema is NOT applied by Terraform — the CI/CD deploy workflow runs `init_db()` as a one-time step after RDS is available

### Phase 3: Security & IAM (Agent)

1. Create IAM module with roles:
   - GitHub Actions OIDC role (trust GitHub's OIDC, repo: ahmedikram/laad)
   - ECS task execution role
   - ECS task role
   - SageMaker execution role
2. Create security groups:
   - ALB SG: 443 (0.0.0.0/0), 80 (0.0.0.0/0) → redirect
   - ECS API SG: 8000 from ALB SG
   - ECS Consumer SG: no ingress needed
   - RDS SG (new): 5432 from ECS API + Consumer SGs
   - **Note**: Existing MLflow RDS SG is NOT modified

### Phase 4: ECR & Secrets (Agent)

1. Create ECR module with 2 repos (image scan on push, lifecycle policy)
2. Create Secrets module with 6 secrets (added `laad/db/master` for the new RDS):
   - `laad/db/master` — Auto-generated RDS credentials (host, port, db, user, password)
   - `laad/db/mlflow` — MLflow RDS credentials (from existing .env)
   - `laad/app/jwt` — JWT secret key
   - `laad/rag/ollama` — Ollama + OpenRouter API keys
   - `laad/mlflow` — MLflow tracking URI + S3 artifact root
   - `laad/app/backend` — All remaining env vars
3. Upload initial placeholder values

### Phase 5: ECS (Agent)

1. Create ECS module with:
   - Cluster (Fargate only)
   - Task definitions (API + Consumer)
   - Services (API + Consumer)
   - ALB + listener + target group
   - CloudWatch log groups

### Phase 6: Frontend (Agent)

1. Create Frontend module with:
   - S3 bucket (private, name: `laad-frontend-<unique-suffix>`)
   - CloudFront distribution with OAC (Origin Access Control)
   - S3 bucket policy granting read to CloudFront only
   - 404 → index.html error response (SPA routing)
   - Output: CloudFront domain name, S3 bucket name

### Phase 7: SageMaker (Agent)

1. Output the S3 URI where the model needs to be uploaded
2. Create SageMaker model, endpoint config, endpoint (conditionally — depends on manual Step 1)

### Phase 8: CI/CD Pipelines (Agent)

Create `.github/workflows/` with:

**`ci.yml`** — On push to any branch:
- Checkout code
- Set up Python 3.10
- Install backend dependencies
- Run: `python -m pytest backend/tests/ -v --tb=short --cov=backend/src --cov=backend/generator --cov=backend/kafka --cov-report=term-missing` (Note: Tests may require a running PostgreSQL test instance in CI — the agent should handle this with `services.postgres` in the workflow)
- Set up Node.js 22
- Install frontend dependencies
- Run: `npx vitest run --coverage` (from frontend/)
- **Manual step**: Tests that require Kafka, Redis, ChromaDB, or Ollama will be skipped/noisily fail in CI. The agent should document which tests need mocking and which should be skipped in CI.

**`cd.yml`** — On push to `main` (after CI):
- Configure AWS credentials via OIDC
- Login to ECR
- Build & push `backend/` → `laad-backend:latest` (ECR)
- Force new ECS deployment for `laad-api-service`

**Frontend deploy step** (within cd.yml):
- Build frontend: `npm run build` in `frontend/`
- Sync to S3: `aws s3 sync frontend/dist s3://laad-frontend-<suffix> --delete`
- Invalidate CloudFront: `aws cloudfront create-invalidation --distribution-id <id> --paths "/*"`

**One-time RDS schema init** (within cd.yml):
- On first deploy, or when `terraform output -raw rds_endpoint` changes:
  ```bash
  python -c "from backend.src.database.init_db import init_db; init_db(force=True)"
  ```
  This requires a runner (GitHub Actions runner) with network access to the RDS. Since the RDS is in private subnets, this step runs **from the ECS task itself** via an AWS CLI command:
  ```bash
  aws ecs run-task --cluster laad-cluster --task-definition laad-api --overrides '{"command": ["python", "-c", "from backend.src.database.init_db import init_db; init_db(force=True)"]}' --launch-type FARGATE --network-configuration ...
  ```

**`terraform.yml`** — On PR or push to main modifying `terraform/*`:
- Configure AWS credentials via OIDC
- `terraform init`
- `terraform plan` (on PR — comment the plan on the PR)
- `terraform apply` (on push to main — auto-approve)

### Phase 9: Backend Code Changes (Agent)

1. **SageMaker inference client**: Add to `ml_detector.py`:
   - New method `_predict_via_sagemaker(features)` using `boto3`
   - Fallback chain: SageMaker → local joblib → heuristic-only
   - Try SageMaker first if `SAGEMAKER_ENDPOINT_NAME` env var is set
   - On timeout/exception → fallback to local model
   - On local model unavailable → fallback to heuristic-only

2. **Graceful degradation for local services**: The following services are NOT deployed to ECS and should degrade gracefully:
   - **ChromaDB**: RAG vector store. If `CHROMA_HOST` is unreachable, the RAG endpoint returns a 503 with message "Vector store unavailable". No crash.
   - **Redis**: Cache. If `REDIS_HOST` is unreachable, the cache module falls back to no-op (no caching). The `redis_client.py` already handles this via `connect_ex` with fallback.
   - **Kafka**: Consumer stays local (your machine). The API doesn't directly depend on Kafka.
   - **Local Docker services (Postgres, Kafka, Redis, Chroma, Ollama)**: The ECS API only needs PostgreSQL + SageMaker + MLflow. All other connections are to cloud APIs (OpenRouter for LLM) or gracefully degrade when local services are unavailable.

   The env var injection from Secrets Manager (`laad/app/backend`) should set these to reasonable defaults that don't reference localhost.

3. **No other backend code changes needed** — env vars already read from `os.environ` via `config.py` modules.

### Phase 10: Verification & Manual Steps (You)

1. Run manual Step 1 (download model from MLflow, upload to S3)
2. Run `terraform apply` to create SageMaker endpoint (now that model data exists)
3. Run manual Step 2 (set JWT secret)
4. Run manual Step 3 (verify ALB health — curl /docs)
5. Run manual Step 4 (set GitHub Actions OIDC variables)
6. Push to main → verify CI/CD pipeline runs (CI passes, CD deploys)
7. Verify ALB DNS + `/docs` — FastAPI Swagger loads and APIs respond
8. Verify frontend — open CloudFront URL in browser, React app loads
9. Verify RDS connectivity — trigger an API call that hits the database (e.g., login or list anomalies). Check CloudWatch Logs for `laad-api` log group.
10. Verify SageMaker — call the anomaly detection endpoint. If SageMaker is stopped, verify the fallback to local joblib model.
11. (Optional) Manual Step 5 if doing Kafka on EC2

**Rollback plan**: If anything fails during Phase 10:
- Terraform state persists all resources. Fix the issue and re-run `terraform apply`.
- If the ECS service is broken, force rollback to the previous task definition revision via AWS Console.
- If the RDS schema is corrupted, run `init_db(force=True)` from a one-shot ECS task.
- If CloudFront or S3 is broken, the ALB DNS still serves the API directly (browser UX degrades but APIs work).

## Architectural Decisions & Rationale

| Decision | Option | Why |
|---|---|---|
| Single NAT Gateway | Cheaper | ~$35/mo vs $70/mo for multi-AZ. Portfolio project, not production. |
| Fargate Spot | Cheaper | ~70% savings vs on-demand. Tasks can be interrupted but for dev/portfolio, acceptable. |
| Self-signed ACM cert | No domain | ACM generates a cert valid for internal/direct ALB use. No domain needed. |
| SageMaker outside VPC | Simpler | No VPC endpoints, NAT for SageMaker. Portfolio project. |
| Single task per service | Cheaper | Portfolio demo load is near-zero. |
| 2 AZs | HA story | Shows understanding of multi-AZ without over-engineering. |
| Separate ECR repos per service | Cleaner | Each service gets its own image, can tag independently. |
| CloudWatch Logs 14-day retention | Cost-saving | AWS charges ~$0.03/GB/month for logs. 14 days is sufficient for debugging. |
| Separate RDS for app/MLflow | Isolation | MLflow metadata stays isolated. Each can be destroyed/recreated independently. |
| S3 + CloudFront for frontend | Best practice | Global CDN, S3 is $0 for storage at this scale, CloudFront ~$1/mo at PriceClass_100. |
| Frontend served via CloudFront OAC | Security | CloudFront pulls from S3 via Origin Access Control — no public S3 access needed. |

## Cost Estimate (Monthly)

| Resource | Cost | Notes |
|---|---|---|
| NAT Gateway | ~$35 | Single-AZ. Largest cost item. |
| ALB | ~$22 | Per-hour charge + LCU costs (near-zero for demo) |
| Fargate API (Spot 1 task) | ~$8 | 1024 CPU / 3072 MB, 730 hrs, Spot savings ~70% |
| Fargate Consumer (Spot 0 tasks) | $0 | If consumer kept local |
| RDS db.t4g.micro (20GB gp3) | ~$15 | PostgreSQL 16, 7-day backup, storage encrypted |
| SageMaker ml.m5.large (auto-stop) | ~$20 | If running ~6 hrs/day, else ~$84 if 24/7 |
| CloudFront (PriceClass_100) | ~$1 | ~0.5 GB/mo data transfer + request charges |
| S3 frontend bucket | ~$0.10 | Minimal storage. CloudFront only origin |
| ECR storage | ~$0.10 | Per GB/month, negligible |
| CloudWatch Logs | ~$3 | 2 log groups, 14-day retention, minimal data |
| ACM certs | $0 | Free |
| Secrets Manager | ~$0.80 | 6 secrets ($0.40/secret), ~$0.05 per 10K API calls |
| S3 Terraform state | ~$0.10 | 1 bucket, versioning, minimal storage |
| DynamoDB (PAY_PER_REQUEST) | ~$0.10 | Lock table, near-zero usage |
| VPC (IP addresses) | $0 | No charge for VPC/subnets |
| **Total (with SageMaker auto-stop)** | **~$105/mo** | NAT Gateway + ALB + RDS are unavoidable |
| **Optimised (stop SageMaker + stop RDS when idle)** | **~$65-80/mo** | Stop non-essential services via cron |

## Risks & Mitigations

| Risk | Mitigation |
|---|---|---|
| Tests require Kafka/Redis/Ollama in CI | Skip integration tests in CI; run unit tests only. Document which tests require local services. |
| SageMaker endpoint fails after MLflow model upgrade | Pin model version in Terraform. Manual update required after retraining. |
| ALB DNS changes if stack recreated | Use Terraform to avoid deletion. Output ALB DNS once. |
| MLflow RDS publicly accessible (current) | Do NOT change this — MLflow local Docker container needs it. The new LAAD RDS is in private subnets. |
| NAT Gateway is single point of failure | Acceptable for portfolio. Document as known limitation. |
| Fargate Spot can be interrupted | Use on-demand if interruption causes issues. For portfolio, Spot is fine. |
| RDS schema init from CI/CD cannot reach private RDS | Run schema init as a one-shot ECS task inside the VPC using `aws ecs run-task`. |
| LAAD app cannot connect to local services (Kafka, Redis, Chroma) from ECS | These stay local. Fargate API only needs PostgreSQL + SageMaker + MLflow (existing RDS). Frontend runs in browser. |
| `db.t4g.micro` may burst CPU credits | For portfolio load, CPU credits will never drain. Monitor `CPUCreditBalance` in CloudWatch. |



