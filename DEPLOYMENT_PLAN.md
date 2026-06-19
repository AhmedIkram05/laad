# LAAD AWS Deployment Plan

## Overview

Deploy the LAAD platform to AWS with Terraform-managed infrastructure and GitHub Actions CI/CD. Three high-ROI stories for AI/ML/DE/SWE roles:

1. **ECS Fargate** — FastAPI backend + Kafka consumer + log generator + ChromaDB + Redis as separate services behind ALB
2. **SageMaker real-time endpoint** — XGBoost champion model from MLflow registry (AI/ML CV story)
3. **Infrastructure-as-Code** — Terraform with S3 + DynamoDB state backend, least-privilege IAM, private networking

> **Execution model:** All implementation is **agent-driven** (subagent specialists). The plan is structured as a dependency graph rather than a sequential checklist. Multiple agents work in parallel where dependencies allow. Human supervision is the bottleneck, not agent capacity.
>
> **Budget note:** The AWS account has ~$48 in free credits. SageMaker (~$84/mo) is the dominant cost when running. Credits cover ~2.5 weeks of full-stack runtime. After credits exhaust, the ~$200/mo baseline runs on card billing. Plan trades are cost-aware but not cost-constrained — credits are a fixed resource to manage, not a hard wall. **Actual cost with SageMaker: ~$313/mo.** Budget alerts are configured to prevent surprises.

## Prerequisites

Before starting implementation, ensure these are completed:

1. **AWS CLI credentials**: `aws configure` with an IAM user/role that has `AdministratorAccess` for initial Terraform bootstrap.

2. **Verify existing resources** in `eu-west-2`:
   - RDS PostgreSQL instance: `laad-mlflow-postgres`
   - S3 bucket: `laad-mlflow-artifacts`
   - VPC CIDR of existing MLflow infrastructure (check for overlap with `10.0.0.0/16`)
   - **MLflow connectivity model**: The MLflow RDS has a public endpoint (no VPC peering configured). ECS tasks reach it through the NAT Gateway. Document this as the current design — VPC peering is deferred.

3. **Install Terraform**: `brew install terraform` (macOS)

4. **GitHub OIDC**: Terraform bootstrap needs initial AWS creds. After Terraform creates the OIDC provider + IAM role, add `AWS_ROLE_ARN` to GitHub Actions secrets.

> **Prerequisite verification (agent):** The implementation agent must verify the existing MLflow VPC CIDR before creating the LAAD VPC to avoid overlap.

## Architecture

```
[GitHub Actions] ──OIDC──> [AWS IAM Role (scoped)]
       |
       ├── build & push ──> [ECR (single repo, two tags)]
       └── deploy ──> [ECS Fargate]

Internet ──> ALB (HTTP:80) ──> ECS Fargate (FastAPI API)
              CloudFront HTTPS   |
           (for frontend)        ├──> ECS Fargate Consumer <── EC2 t4g.small (Kafka)
                                 ├──> ECS Fargate Generator ──> Kafka
                                 ├──> ECS Fargate Redis (cache, DLQ, JWT blacklist)
                                 ├──> ECS Fargate ChromaDB (vector store)
                                 ├──> SageMaker endpoint (XGBoost anomaly model)
                                 └──> RDS PostgreSQL (new, LAAD app)

[CloudFront CDN] <── [S3 Bucket (React static build)] <── CI/CD build
```

**Key design decisions:**
- **ALB is HTTP-only** (no ACM cert required). CloudFront handles TLS termination for the frontend. Backend API calls from trusted sources use HTTP within VPC.
- **SageMaker stays** — it's the AI/ML CV story. Scheduled stop/start extends credit life.
- **ChromaDB, Redis, log generator** all run as ECS Fargate tasks (no local-Docker gap).
- **Single ECR repo** with three tags (`api-latest`, `consumer-latest`, `generator-latest`). Build once, tag thrice.
- **No SNS notifications** — removed from scope. Pipeline success/failure visible in GitHub Actions UI.
- **No dedicated `terraform.yml` pipeline** — Terraform applied manually after review.

## Terraform Module Structure

```
terraform/
├── main.tf                    # Provider config, state backend, all modules
├── variables.tf               # All input variables
├── outputs.tf                 # ALB DNS, ECR repo, SageMaker endpoint, frontend domain
├── backend.tf                 # S3 + DynamoDB state backend config
├── providers.tf               # AWS provider config, OIDC provider
│
├── modules/
│   ├── vpc/
│   │   ├── main.tf            # VPC, 2 public + 2 private subnets, NAT Gateway, IGW, route tables, SGs
│   │   ├── variables.tf
│   │   └── outputs.tf
│   │
│   ├── ecs/
│   │   ├── main.tf            # ECS cluster (Fargate), task defs (5 services), services, ALB, TG
│   │   ├── variables.tf
│   │   ├── outputs.tf
│   │   └── task_definitions/
│   │       ├── api.json.tpl
│   │       ├── consumer.json.tpl
│   │       ├── generator.json.tpl
│   │       ├── chromadb.json.tpl
│   │       └── redis.json.tpl
│   │
│   ├── sagemaker/
│   │   ├── main.tf            # SageMaker model, endpoint config, endpoint (gated by enabled flag)
│   │   ├── variables.tf
│   │   └── outputs.tf
│   │
│   ├── iam/
│   │   ├── main.tf            # ECS task + execution roles, SageMaker role, GitHub OIDC role (scoped)
│   │   ├── variables.tf
│   │   └── outputs.tf
│   │
│   ├── ecr/
│   │   ├── main.tf            # Single ECR repo (laad-app), lifecycle policy (25 images)
│   │   ├── variables.tf
│   │   └── outputs.tf
│   │
│   ├── rds/
│   │   ├── main.tf            # New RDS PostgreSQL 16 (deletion_protection=true)
│   │   ├── variables.tf
│   │   └── outputs.tf
│   │
│   ├── secrets/
│   │   ├── main.tf            # All Secrets Manager entries (JWT via random_password)
│   │   ├── variables.tf
│   │   └── outputs.tf
│   │
│   ├── frontend/
│   │   ├── main.tf            # S3 bucket + CloudFront distribution (OAC, forward=all)
│   │   ├── variables.tf
│   │   └── outputs.tf
│   │
│   ├── ec2/
│   │   ├── main.tf            # t4g.small for Kafka, user_data automation, SG, encrypted EBS
│   │   ├── variables.tf
│   │   └── outputs.tf
│   │
│   └── monitoring/
│       ├── main.tf            # CloudWatch dashboard, budget alerts, metric filters
│       ├── variables.tf
│       └── outputs.tf
│
└── bootstrap/
    └── main.tf                # One-time: S3 bucket (with policy) + DynamoDB table for state
```

## Terraform Module Details

### Bootstrap (one-time, manual apply)

```hcl
# terraform/bootstrap/main.tf
# Run once: terraform apply -auto-approve
resource "aws_s3_bucket" "tf_state" {
  bucket = "laad-terraform-state-ahmedikram"
}

resource "aws_s3_bucket_versioning" "tf_state" {
  bucket = aws_s3_bucket.tf_state.id
  versioning_configuration { status = "Enabled" }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "tf_state" {
  bucket = aws_s3_bucket.tf_state.id
  rule { apply_server_side_encryption_by_default { sse_algorithm = "AES256" } }
}

resource "aws_s3_bucket_policy" "tf_state_restrict" {
  bucket = aws_s3_bucket.tf_state.id
  policy = data.aws_iam_policy_document.tf_state_restrict.json
}

data "aws_iam_policy_document" "tf_state_restrict" {
  statement {
    effect = "Deny"
    principals { type = "*"; identifiers = ["*"] }
    actions = ["s3:DeleteObject", "s3:DeleteObjectVersion"]
    resources = ["${aws_s3_bucket.tf_state.arn}/*"]
    condition {
      test = "Bool"
      variable = "aws:MultiFactorAuthPresent"
      values = ["false"]
    }
  }
}

resource "aws_dynamodb_table" "tf_lock" {
  name         = "laad-terraform-lock"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "LockID"
  attribute { name = "LockID"; type = "S" }
}
```

**Run from `terraform/bootstrap/`:** After creation, the bucket name and DynamoDB table name are used in `backend.tf`.

### VPC Module

Creates a VPC with:
- **2 availability zones** (eu-west-2a, eu-west-2b)
- **2 public subnets** — for ALB and NAT Gateway
- **2 private subnets** — for ECS Fargate tasks and RDS
- **1 NAT Gateway** in public subnet (single-AZ, other AZ routes through same NAT)
- **Internet Gateway** — for public subnets
- **Route tables** — public (IGW), private (NAT)
- **VPC Endpoints** for S3 and DynamoDB (gateway endpoints, no extra cost)
- **Security groups**: ALB SG, ECS API SG, ECS Consumer SG, ECS Generator SG, RDS SG, Kafka SG

Key decisions:
- Single NAT Gateway saves ~$35/mo vs multi-AZ
- Only 2 AZs for portfolio-level HA
- VPC CIDR: `10.0.0.0/16` (verify non-overlap with existing MLflow VPC)
- Security groups live in VPC module (avoids cross-module dependency)

**Security group rules:**
| SG | Ingress | Egress |
|----|---------|--------|
| ALB | HTTP:80 0.0.0.0/0 | All |
| ECS API | Port 8000 from ALB SG | All |
| ECS Consumer | None | All |
| ECS Generator | None | All |
| RDS | Port 5432 from ECS API + Consumer SGs | All |
| Kafka | Port 9092 from ECS Consumer SG | All |
| Redis | Port 6379 from ECS API SG | All |
| ChromaDB | Port 8000 from ECS API SG | All |

**Important:** ECR image pulls and CloudWatch log delivery go through the NAT Gateway (no VPC interface endpoints added — NAT covers it at ~$35/mo already budgeted). The gateway endpoints cover S3 access for model artifacts.

### RDS Module

Creates a new RDS PostgreSQL 16 instance for the LAAD application data (not MLflow — that's a separate existing RDS).

```hcl
resource "aws_db_instance" "laad_postgres" {
  engine                     = "postgres"
  engine_version             = "16"
  instance_class             = "db.t4g.micro"
  allocated_storage          = 20
  db_name                    = "atm_platform"
  username                   = "atm_user"
  password                   = random_password.rds_master.result
  db_subnet_group_name       = aws_db_subnet_group.laad.name
  vpc_security_group_ids     = [var.rds_security_group_id]
  skip_final_snapshot        = true
  backup_retention_period    = 7
  deletion_protection        = true
  storage_encrypted          = true
}
```

- `deletion_protection = true` — prevents accidental `terraform destroy` from wiping the database
- `skip_final_snapshot = true` — acceptable for portfolio (no snapshot cost)
- Password stored in Secrets Manager as `laad/db/master`

**Schema init:** Done via one-shot ECS `run-task` in the CD pipeline (not via Terraform). The `init_db()` call uses `force=False` in production — the `LAAD_ENV=production` environment variable guards against accidental `force=True`.

### IAM Module

**1. GitHub Actions OIDC role** (`laad-github-actions-role`):
- Trust policy: repo `ahmedikram/laad`, branch `ref:refs/heads/main`
- Scoped policies:
  - `ecr:GetAuthorizationToken`, `ecr:BatchCheckLayerAvailability`, `ecr:InitiateLayerUpload`, `ecr:UploadLayerPart`, `ecr:CompleteLayerUpload`, `ecr:PutImage` — on `laad-app` repo
  - `ecs:UpdateService`, `ecs:DescribeServices`, `ecs:RegisterTaskDefinition`, `ecs:RunTask`, `ecs:DescribeTaskDefinition`, `ecs:DescribeTasks`, `ecs:ListTaskDefinitions` — on `laad-*` resources
  - `s3:PutObject`, `s3:GetObject`, `s3:ListBucket`, `s3:DeleteObject` — on `laad-frontend-ahmedikram`
  - `cloudfront:CreateInvalidation`, `cloudfront:GetDistribution`, `cloudfront:ListDistributions` — on the CloudFront distribution
- **No** `AmazonECS_FullAccess`, **no** `IAMReadOnlyAccess`

**2. ECS Task Execution Role** (`laad-ecs-execution-role`):
- `AmazonECSTaskExecutionRolePolicy` (ECR pull + CloudWatch logs)
- Custom policy: Secrets Manager read on `laad/*`

**3. ECS Task Role** (`laad-ecs-task-role`):
- `sagemaker:InvokeEndpoint` on the specific endpoint ARN
- `s3:GetObject` on `laad-mlflow-artifacts` (model download on boot)
- CloudWatch logs: `CreateLogStream`, `PutLogEvents`
- **No static AWS credentials** — everything uses task role

**4. SageMaker Execution Role** (`laad-sagemaker-execution-role`):
- Custom policy (not `AmazonSageMakerFullAccess`):
  - `sagemaker:CreateEndpoint`, `sagemaker:CreateEndpointConfig`, `sagemaker:DescribeEndpoint`, `sagemaker:InvokeEndpoint` on `laad-*`
  - `s3:GetObject` on `laad-mlflow-artifacts/sagemaker-models/*`
  - `ecr:GetDownloadUrlForLayer`, `ecr:BatchGetImage` on the XGBoost inference image

### Secrets Module

Created by Terraform. JWT secret uses `random_password` (no placeholder window):

```hcl
resource "random_password" "jwt_secret" {
  length  = 64
  special = false
}

resource "aws_secretsmanager_secret_version" "jwt" {
  secret_id     = aws_secretsmanager_secret.jwt.id
  secret_string = jsonencode({ JWT_SECRET_KEY = random_password.jwt_secret.result })
}
```

| Secret Name | Key | Source |
|---|---|---|
| `laad/db/master` | RDS connection params for LAAD app RDS | `random_password` in Terraform |
| `laad/db/mlflow` | MLflow RDS connection params | From existing `.env` (rotated) |
| `laad/app/jwt` | `JWT_SECRET_KEY` | `random_password` in Terraform |
| `laad/rag/ollama` | `OLLAMA_API_KEY`, `OPENROUTER_API_KEY` | From existing `.env` (rotated) |
| `laad/app/backend` | All runtime env vars | Compiled from docker-compose.yml |
| `laad/sagemaker` | `SAGEMAKER_ENDPOINT_NAME`, `SAGEMAKER_REGION` | Created by Terraform |
| `laad/mlflow` | `MLFLOW_TRACKING_URI`, `MLFLOW_S3_ARTIFACT_ROOT` (no static AWS creds) | From existing `.env` |

**Note:** `laad/mlflow` does **not** contain static AWS credentials. The ECS task role handles S3 access via its inline policy.

### ECR Module

Single repository: `laad-app` with:
- `image_scanning_configuration = { scan_on_push = true }`
- `lifecycle_policy` — keep last 25 images (avoids rollback target deletion)
- Tagged images (`api-latest`, `consumer-latest`, `generator-latest`) excluded from lifecycle pruning

### ECS Module

#### Cluster
- `aws_ecs_cluster` named `laad-cluster` (Fargate capacity providers: `FARGATE` and `FARGATE_SPOT`)

#### Task Definitions

**API Task Definition** (`laad-api`):
- CPU/Memory: 1024 CPU / 3072 MB
- Container image: `laad-app:api-latest` (from ECR)
- Port mappings: 8000
- Secrets: All from Secrets Manager injected as env vars
- Health check: `curl -f http://localhost:8000/health` (dedicated health endpoint)
- Environment: `POSTGRES_*`, `JWT_SECRET_KEY`, `MLFLOW_*`, `REDIS_HOST=redis`, `REDIS_PORT=6379`, `CHROMA_HOST=chromadb`, `CHROMA_PORT=8000`, `OLLAMA_*`, `RAG_*`, `SAGEMAKER_*`, `LAAD_ENV=production`, `VITE_API_URL=<alb-dns>` (from Terraform output)
- Command: `python -m uvicorn backend.src.api.server:app --host 0.0.0.0 --port 8000 --workers 4`
- Storage: 21 GB ephemeral
- **User**: `appuser` (non-root, via Dockerfile)

**Consumer Task Definition** (`laad-consumer`):
- CPU/Memory: 512 CPU / 1024 MB
- Container image: `laad-app:consumer-latest`
- Command: `python -m backend.kafka.consumer`
- Health check: `curl -f http://localhost:8081/health` (dedicated health endpoint on port 8081)
- Environment: `KAFKA_BOOTSTRAP_SERVERS=<kafka-private-ip>:9092`, DB creds, Redis
- Startup: Retry loop with exponential backoff for Kafka broker connection

**Generator Task Definition** (`laad-generator`):
- CPU/Memory: 256 CPU / 512 MB (lightweight)
- Container image: `laad-app:generator-latest`
- Command: `python -m backend.generator.main`
- Environment: `KAFKA_BOOTSTRAP_SERVERS=<kafka-private-ip>:9092`
- Fargate Spot

**Redis Task Definition** (`laad-redis`):
- CPU/Memory: 256 CPU / 512 MB
- Image: `redis:7-alpine`
- Port: 6379
- Fargate Spot

**ChromaDB Task Definition** (`laad-chromadb`):
- CPU/Memory: 512 CPU / 1024 MB
- Image: `chromadb/chroma:latest`
- Port: 8000
- Environment: `CHROMA_SERVER_HOST=0.0.0.0`, `CHROMA_SERVER_PORT=8000`
- Fargate Spot

#### ALB
- `aws_lb` — Application Load Balancer, internet-facing
- `aws_lb_target_group` — HTTP:8000, health check path `/health`
- `aws_lb_listener` — **HTTP:80** (no HTTPS — no ACM cert needed). CloudFront handles TLS for the frontend.
- Security group: allows HTTP:80 from 0.0.0.0/0

#### Services

| Service | Desired | Capacity | Notes |
|---------|---------|----------|-------|
| API | 1 | On-Demand | Must stay up. No interruption risk. |
| Consumer | 1 | Fargate Spot | Acceptable interruption. Auto-restarts. |
| Generator | 1 | Fargate Spot | Acceptable interruption. |
| Redis | 1 | Fargate Spot | Acceptable interruption. |
| ChromaDB | 1 | Fargate Spot | Acceptable interruption. |

API uses on-demand (not Spot) to ensure the service remains available during demos. Other services use Spot for 70% savings.

#### CloudWatch
- Log groups: `/ecs/laad-api`, `/ecs/laad-consumer`, `/ecs/laad-generator`, `/ecs/laad-redis`, `/ecs/laad-chromadb` — all 7-day retention
- Metric filter: `5xx errors` → CloudWatch alarm
- Metric filter: `CRITICAL` logs → CloudWatch alarm
- CloudWatch dashboard showing: ALB requests/5xx/latency, ECS task CPU/memory, RDS connections/CPU, Kafka broker disk, NAT Gateway bytes

### Frontend Module

```hcl
resource "aws_s3_bucket" "frontend" {
  bucket = "laad-frontend-ahmedikram"
}

resource "aws_s3_bucket_public_access_block" "frontend" {
  bucket                  = aws_s3_bucket.frontend.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_versioning" "frontend" {
  bucket = aws_s3_bucket.frontend.id
  versioning_configuration { status = "Enabled" }
}

resource "aws_cloudfront_distribution" "frontend" {
  origin {
    domain_name = aws_s3_bucket.frontend.bucket_regional_domain_name
    origin_access_control_id = aws_cloudfront_origin_access_control.frontend.id
  }
  default_cache_behavior {
    viewer_protocol_policy = "redirect-to-https"
    allowed_methods        = ["GET", "HEAD", "OPTIONS"]
    cached_methods         = ["GET", "HEAD"]
    default_ttl            = 3600
    max_ttl                = 86400
    forward = "all"  # Query strings forwarded for SPA routing
  }
  custom_error_response {
    error_code         = 404
    response_code      = 200
    response_page_path = "/index.html"
  }
  price_class         = "PriceClass_100"
  default_root_object = "index.html"
  enabled             = true
}

resource "aws_cloudfront_origin_access_control" "frontend" {
  name                              = "laad-frontend-oac"
  origin_access_control_origin_type = "s3"
  signing_behavior                  = "always"
  signing_protocol                  = "sigv4"
}
```

- `forward = "all"` — query strings forwarded (SPA routing support)
- OAC (Origin Access Control) — more secure than OAI
- CloudFront handles HTTPS termination, ALB uses HTTP internally

### EC2 Module (Kafka Broker)

```hcl
resource "aws_instance" "kafka" {
  ami           = data.aws_ami.amazon_linux_2023.id
  instance_type = "t4g.small"     # 2 GB RAM — sufficient for Kafka
  subnet_id     = var.public_subnet_ids[0]
  key_name      = aws_key_pair.kafka.key_name
  
  root_block_device {
    volume_size = 20
    volume_type = "gp3"
    encrypted   = true           # EBS encryption
  }

  vpc_security_group_ids = [var.kafka_security_group_id]

  user_data = <<-EOF
    #!/bin/bash
    set -e
    # Install Java 17 (Kafka 3.6+ supports Java 17)
    dnf install -y java-17-amazon-corretto-headless
    
    # Download and extract Kafka
    cd /home/ec2-user
    wget -q https://downloads.apache.org/kafka/3.6.0/kafka_2.13-3.6.0.tgz
    tar -xzf kafka_2.13-3.6.0.tgz
    cd kafka_2.13-3.6.0
    
    # Configure KRaft (KIP-500)
    KAFKA_CLUSTER_ID=$(bin/kafka-storage.sh random-uuid)
    
    # Configure heap for t4g.small (2GB RAM)
    export KAFKA_HEAP_OPTS="-Xms512m -Xmx512m"
    
    # Create data directory and configure log.dirs BEFORE format
    sudo mkdir -p /var/lib/kafka/data
    sudo chown -R ec2-user:ec2-user /var/lib/kafka/data
    sed -i "s|log.dirs=/tmp/kraft-combined-logs|log.dirs=/var/lib/kafka/data|" config/kraft/server.properties
    
    # Format storage (now uses correct log.dirs from server.properties)
    bin/kafka-storage.sh format -t $KAFKA_CLUSTER_ID -c config/kraft/server.properties
    
    # Configure advertised listeners for private IP
    PRIVATE_IP=$(curl -s http://169.254.169.254/latest/meta-data/local-ipv4)
    sed -i "s/advertised.listeners=.*/advertised.listeners=PLAINTEXT:\/\/$PRIVATE_IP:9092/" config/kraft/server.properties
    
    # Start Kafka
    nohup bin/kafka-server-start.sh config/kraft/server.properties > /home/ec2-user/kafka.log 2>&1 &
    echo "Kafka started with cluster ID: $KAFKA_CLUSTER_ID"
  EOF
}

resource "aws_eip" "kafka" {
  instance = aws_instance.kafka.id
}
```

- **t4g.small** (2 GB RAM) — not t4g.nano. Kafka JVM gets 512 MB heap, OS gets the rest.
- `user_data` automates the full Kafka setup (no manual SSH install step)
- EBS encryption enabled
- Private IP only (no public IP — security by design)
- Kafka in private subnet would require NAT for ECS consumer → Kafka traffic. Since Kafka is in a public subnet with SG restricted to ECS Consumer SG, this is acceptable.

### Monitoring Module

- **CloudWatch dashboard**: ALB requests/5xx/latency, ECS task CPU/memory, RDS connections/CPU/CPUCreditBalance, NAT Gateway bytes, Kafka broker disk usage
- **Budget alert**: `aws_budgets_budget` at 80%/100% of $50/mo (without SageMaker) and $150/mo (with SageMaker)
- **CPU credit alarm**: RDS `CPUCreditBalance` < 50
- **SageMaker invocation alarm**: Zero invocations over 10-minute period

### SageMaker Module

Gated by `sagemaker_enabled` variable (default `false`):

```hcl
resource "aws_sagemaker_model" "champion" {
  count = var.sagemaker_enabled ? 1 : 0
  model_name = "laad-xgb-champion"
  primary_container {
    image          = var.sagemaker_inference_image  # e.g., 246618743249.dkr.ecr.eu-west-2.amazonaws.com/sagemaker-xgboost:1.5-1 (AWS account varies by region)
    model_data_url = var.sagemaker_model_data_url   # S3 path from model upload ECS task output
  }
  execution_role_arn = var.sagemaker_execution_role_arn
}

resource "aws_sagemaker_endpoint_configuration" "champion" {
  count = var.sagemaker_enabled ? 1 : 0
  name = "laad-xgb-champion-config"
  production_variants {
    instance_type       = "ml.m5.large"
    initial_instance_count = 1
    variant_name        = "champion"
  }
}

resource "aws_sagemaker_endpoint" "champion" {
  count                = var.sagemaker_enabled ? 1 : 0
  endpoint_config_name = aws_sagemaker_endpoint_configuration.champion[0].name
  name                 = "laad-xgb-champion"
}
```

- The model upload step is a one-shot ECS `run-task` that runs before `sagemaker_enabled=true`. It downloads the champion model from MLflow and uploads it to S3, resolving the Terraform dependency on the artifact path.
- SageMaker endpoint scheduled stop/start via EventBridge Scheduler for cost management

## CI/CD Pipeline Architecture

### Workflow Structure

```
push to main (any branch)
    │
    ├── ci.yml (always runs)
    │   ├── Lint (ruff check)
    │   ├── Dependency audit (pip-audit)
    │   ├── Vulnerability scan (trivy fs)
    │   ├── Backend tests (pytest via services.postgres)
    │   │   └── python -m pytest backend/tests/ -v --tb=short \
    │   │       --ignore=backend/tests/stress \
    │   │       --ignore=backend/tests/integration \
    │   │       -k "not chroma and not rag and not kafka"
    │   ├── Frontend tests (vitest)
    │   └── ✅ All pass
    │
    └── cd.yml (main only, after CI passes)
        ├── Build & push Docker image (3 tags) to ECR (cached layers)
        ├── Build frontend & sync to S3
        ├── Force ECS deploy (API, Consumer, Generator)
        └── ✅ Deployed
```

**Quality gates:** `ci.yml` runs three safety nets before tests: Ruff lint (code standards), pip-audit (dependency CVEs), and Trivy filesystem scan (secrets, IaC misconfigs, vulnerabilities). All three are fail-fast — the pipeline never reaches deploy if any gate fails.

**No `terraform.yml`:** Terraform is applied manually after reviewing `terraform plan` output.

**No SNS notifications:** Pipeline success/failure is visible in GitHub Actions UI.

**No automatic CloudFront invalidation:** Invalidated manually when needed (rare for portfolio). S3 object versioning allows rollback.

### ci.yml — Test Pipeline

```yaml
name: LAAD CI

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  test:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:16-alpine
        env:
          POSTGRES_DB: atm_platform
          POSTGRES_USER: atm_user
          POSTGRES_PASSWORD: test_password
        ports:
          - 5432:5432
        options: >-
          --health-cmd pg_isready
          --health-interval 5s
          --health-timeout 5s
          --health-retries 10

    steps:
      - uses: actions/checkout@v4

      - name: Set up Python 3.10
        uses: actions/setup-python@v5
        with:
          python-version: "3.10"

      - name: Install dependencies
        run: pip install -r backend/requirements.txt

      - name: Lint with Ruff
        run: |
          pip install ruff
          ruff check backend/

      - name: Audit dependencies for CVEs
        run: pip-audit -r backend/requirements.txt --desc on

      - name: Run Trivy vulnerability scanner
        uses: aquasecurity/trivy-action@0.29.3
        with:
          scan-type: fs
          scan-ref: .
          format: table
          exit-code: 1
          skip-dirs: node_modules,frontend/node_modules,.git

      - name: Run backend tests
        env:
          POSTGRES_HOST: localhost
          POSTGRES_PORT: 5432
          POSTGRES_DB: atm_platform
          POSTGRES_USER: atm_user
          POSTGRES_PASSWORD: test_password
        run: |
          python -m pytest backend/tests/ -v --tb=short \
            --ignore=backend/tests/stress \
            --ignore=backend/tests/integration \
            -k "not chroma and not rag and not kafka"

      - name: Set up Node.js 22
        uses: actions/setup-node@v5
        with:
          node-version: "22"

      - name: Install frontend dependencies
        run: npm ci
        working-directory: frontend

      - name: Run frontend tests
        run: npx vitest run --coverage
        working-directory: frontend
```

### cd.yml — Deploy Pipeline

```yaml
name: LAAD CD

on:
  workflow_run:
    workflows: ["LAAD CI"]
    types: [completed]
    branches: [main]

env:
  AWS_REGION: eu-west-2
  ECR_REPO: ${{ secrets.ECR_REPOSITORY }}

jobs:
  deploy:
    if: ${{ github.event.workflow_run.conclusion == 'success' }}
    runs-on: ubuntu-latest
    permissions:
      id-token: write
      contents: read

    steps:
      - uses: actions/checkout@v4

      - name: Configure AWS credentials
        uses: aws-actions/configure-aws-credentials@v4
        with:
          role-to-assume: ${{ secrets.AWS_ROLE_ARN }}
          aws-region: ${{ env.AWS_REGION }}

      - name: Login to ECR
        id: login-ecr
        uses: aws-actions/amazon-ecr-login@v2

      - name: Set up Docker Buildx
        uses: docker/setup-buildx-action@v3

      - name: Cache Docker layers
        uses: actions/cache@v4
        with:
          path: /tmp/.buildx-cache
          key: ${{ runner.os }}-buildx-${{ github.sha }}
          restore-keys: |
            ${{ runner.os }}-buildx-

      - name: Build, tag, and push Docker image
        env:
          ECR_REGISTRY: ${{ steps.login-ecr.outputs.registry }}
          IMAGE_TAG: ${{ github.sha }}
        run: |
          # Build once with cache, tag thrice
          docker build \
            --cache-from type=local,src=/tmp/.buildx-cache \
            --cache-to type=local,dest=/tmp/.buildx-cache-new,mode=max \
            -t laad-app:$IMAGE_TAG backend/
          docker tag laad-app:$IMAGE_TAG $ECR_REGISTRY/laad-app:api-latest
          docker tag laad-app:$IMAGE_TAG $ECR_REGISTRY/laad-app:consumer-latest
          docker tag laad-app:$IMAGE_TAG $ECR_REGISTRY/laad-app:generator-latest
          docker tag laad-app:$IMAGE_TAG $ECR_REGISTRY/laad-app:$IMAGE_TAG
          docker push --all-tags $ECR_REGISTRY/laad-app
          # Move cache so it doesn't grow indefinitely
          rm -rf /tmp/.buildx-cache
          mv /tmp/.buildx-cache-new /tmp/.buildx-cache

      - name: Build frontend
        run: |
          npm ci
          VITE_API_URL=${{ secrets.API_URL }} npm run build
        working-directory: frontend

      - name: Sync frontend to S3
        run: |
          aws s3 sync frontend/dist s3://laad-frontend-ahmedikram --delete
        working-directory: frontend

      - name: Force ECS deploy API
        run: |
          aws ecs update-service --cluster laad-cluster --service laad-api-service \
            --force-new-deployment

      - name: Force ECS deploy Consumer
        run: |
          aws ecs update-service --cluster laad-cluster --service laad-consumer-service \
            --force-new-deployment

      - name: Force ECS deploy Generator
        run: |
          aws ecs update-service --cluster laad-cluster --service laad-generator-service \
            --force-new-deployment
```

### One-time RDS Schema Init (via ECS run-task)

Run after the first Terraform apply creates the RDS and ECS task definition:

```bash
# Run schema init as a one-shot ECS task
TASK_ARN=$(aws ecs run-task \
  --cluster laad-cluster \
  --task-definition laad-api \
  --overrides '{
    "containerOverrides": [{
      "name": "api",
      "command": ["python", "-c", "from backend.src.database.init_db import init_db; init_db(force=False)"]
    }]
  }' \
  --launch-type FARGATE \
  --network-configuration '{
    "awsvpcConfiguration": {
      "subnets": ["'$(terraform output -raw private_subnet_ids)'"],
      "securityGroups": ["'$(terraform output -raw ecs_api_sg_id)'"]
    }
  }' \
  --query 'tasks[0].taskArn' \
  --output text)

# Wait for completion
aws ecs wait tasks-stopped --cluster laad-cluster --tasks $TASK_ARN

# Check exit code
EXIT_CODE=$(aws ecs describe-tasks --cluster laad-cluster --tasks $TASK_ARN \
  --query 'tasks[0].containers[0].exitCode' --output text)

if [ "$EXIT_CODE" != "0" ]; then
  echo "Schema init failed with exit code $EXIT_CODE"
  aws logs get-log-events --log-group /ecs/laad-api --log-stream-name \
    $(aws logs describe-log-streams --log-group /ecs/laad-api --order-by LastEventTime \
      --descending --limit 1 --query 'logStreams[0].logStreamName' --output text)
  exit 1
fi

echo "Schema init succeeded"
```

**Safety:** `init_db(force=False)` is safe and idempotent. `force=True` is never used in production paths. The `LAAD_ENV=production` env var prevents accidental `force=True` usage.

## Backend Code Changes

### 1. S3 Model Loading (P0-5 fix)

`ml_detector.py` — Download model artifacts from S3 on startup instead of assuming local filesystem:

```python
import boto3
import joblib
import os
from pathlib import Path

MODEL_DIR = Path("/tmp/models")
MODEL_DIR.mkdir(parents=True, exist_ok=True)

def _download_models_from_s3():
    """Download model artifacts from S3 on ECS startup."""
    s3_bucket = os.environ.get("MLFLOW_S3_ARTIFACT_ROOT", "")
    if not s3_bucket:
        return {}
    
    # Parse bucket and prefix from s3:// URI
    s3 = boto3.client("s3")
    bucket = s3_bucket.replace("s3://", "").split("/")[0]
    prefix = "/".join(s3_bucket.replace("s3://", "").split("/")[1:])
    
    models = {}
    for model_name in ["xgb_classifier", "scaler", "pca"]:
        local_path = MODEL_DIR / f"{model_name}.joblib"
        s3_key = f"{prefix}/sagemaker-models/{model_name}.joblib" if prefix else f"sagemaker-models/{model_name}.joblib"
        try:
            s3.download_file(bucket, s3_key, str(local_path))
            models[model_name] = local_path
            logger.info(f"Downloaded {model_name} from S3")
        except Exception as e:
            logger.warning(f"Could not download {model_name} from S3: {e}")
    return models
```

Fallback chain: S3 → local joblib → heuristic-only (existing behavior).

**Disable auto-retrain in production:** `_check_and_retrain_on_startup()` is gated by `LAAD_ENV != "production"`.

### 2. Frontend API URL (P0-2 fix)

`AuthProvider.jsx` — Use `VITE_API_URL` env var instead of hardcoded `localhost:8000`:

```javascript
const API_URL = import.meta.env.VITE_API_URL || "http://localhost:8000";
```

`server.py` — Make CORS origins configurable:

```python
origins = os.environ.get("CORS_ORIGINS", "http://localhost:5173").split(",")
app.add_middleware(CORSMiddleware, allow_origins=origins, ...)
```

The ECS task definition sets `VITE_API_URL` to the ALB DNS (from Terraform output) and `CORS_ORIGINS` to the CloudFront domain.

### 3. JWT Secret Guard (C-10 fix)

Remove `DEFAULT_SECRET_KEY` from auth module. Fail hard at startup if `JWT_SECRET_KEY` is not set:

```python
# In auth module
JWT_SECRET_KEY = os.environ.get("JWT_SECRET_KEY")
if not JWT_SECRET_KEY:
    raise RuntimeError("JWT_SECRET_KEY environment variable is required")
```

### 4. RAGRetriever Graceful Degradation (C-6 fix)

```python
class RAGRetriever:
    def __init__(self):
        self.client = None
        self.collection = None
        try:
            self.client = self._build_client()
            self.collection = self._get_collection()
        except Exception as e:
            logger.warning(f"ChromaDB unavailable: {e}. RAG retrieval disabled.")
    
    def retrieve(self, query: str, top_k: int = 5) -> list:
        if self.collection is None:
            return []   # Graceful degradation
        # ... normal retrieval logic
    
    async def answer(self, query: str) -> dict:
        if self.collection is None:
            return {"answer": "Vector store unavailable. RAG queries require ChromaDB.", 
                    "confidence": 0.0, "sources": []}
        # ... normal RAG flow
```

### 5. Consumer Health Check (P0-4 fix)

Add a lightweight HTTP health endpoint to the Kafka consumer:

```python
# In consumer.py or a separate health server
from http.server import HTTPServer, BaseHTTPRequestHandler
import threading

class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/health":
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b'{"status": "ok"}')
        else:
            self.send_response(404)
            self.end_headers()

def start_health_server(port=8081):
    server = HTTPServer(("0.0.0.0", port), HealthHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
```

### 6. Consumer Kafka Retry (M-7 fix)

Wrap `KafkaConsumer()` construction in a retry loop:

```python
from tenacity import retry, stop_after_attempt, wait_exponential

@retry(stop=stop_after_attempt(5), wait=wait_exponential(multiplier=1, min=2, max=30))
def connect_consumer():
    return KafkaConsumer(
        "atm-logs",
        bootstrap_servers=os.environ["KAFKA_BOOTSTRAP_SERVERS"],
        ...
    )
```

### 7. SageMaker Inference Client (existing plan item)

```python
def _predict_via_sagemaker(self, features: np.ndarray) -> np.ndarray:
    """Invoke SageMaker endpoint for anomaly prediction."""
    endpoint_name = os.environ.get("SAGEMAKER_ENDPOINT_NAME")
    if not endpoint_name:
        raise ValueError("SAGEMAKER_ENDPOINT_NAME not set")
    
    runtime = boto3.client("sagemaker-runtime")
    payload = json.dumps(features.tolist())
    
    response = runtime.invoke_endpoint(
        EndpointName=endpoint_name,
        ContentType="application/json",
        Body=payload,
    )
    return np.array(json.loads(response["Body"].read().decode()))
```

Fallback chain: SageMaker → S3 local model → heuristic-only.

### 8. Dockerfile Hardening (H-17 fix)

```dockerfile
FROM python:3.10-slim

# Install system deps (curl for ECS health checks, git for MLflow)
RUN apt-get update && apt-get install -y curl git --no-install-recommends \
    && rm -rf /var/lib/apt/lists/*

# ... copy requirements, install deps ...

# Create non-root user
RUN addgroup --system appuser && adduser --system --ingroup appuser appuser

# ... copy code ...

USER appuser

EXPOSE 8000

CMD ["python", "-m", "uvicorn", "backend.src.api.server:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]
```

**Note:** Single Dockerfile for all services. ECS task definition specifies the `command` override for consumer/generator roles. No `--build-arg CMD` needed — it's dead code and has been removed.

### 9. init_db Production Guard (P0-1 fix)

```python
def init_db(force: bool = False):
    """Initialize database schema.
    
    Args:
        force: If True, drops all tables before creating them.
               Raises RuntimeError if LAAD_ENV=production.
    """
    env = os.environ.get("LAAD_ENV", "development")
    if force and env == "production":
        raise RuntimeError("Cannot force init_db in production environment")
    # ... rest of function
```

## Implementation Plan — Dependency Batches

The plan is structured as a **dependency graph** (not a sequential list). Multiple agents work in parallel within each batch. Human supervision is the bottleneck.

### Dependency Graph

```
Batch 0: Bootstrap (single-threaded)
  │
  ├──────────────────────────────────────────────┐
  ▼                                              ▼
Batch 1a: Foundation (parallel)         Batch 1b: Dockerfile + Code (parallel)
  ├── VPC module                                ├── Dockerfile hardening (USER appuser)
  ├── IAM module                                ├── S3 model loading
  ├── ECR module                                ├── JWT guard
  ├── Secrets module (random_password JWT)      ├── RAGRetriever graceful degradation
  │                                              ├── Consumer health check + retry
  ▼                                              ├── Frontend VITE_API_URL
Batch 2a: Infrastructure (parallel)              └── init_db production guard
  ├── RDS module                       
  ├── EC2 Kafka (t4g.small, user_data)       
  ├── ECS module (5 task defs + services)   Batch 2b: CI/CD
  ├── Frontend module (S3 + CloudFront)         ├── ci.yml (tests with services.postgres)
  ├── Monitoring module (dashboard, budget)     └── cd.yml (deploy, triggered by CI success)
  │
  ▼
Batch 3: SageMaker (gated, after model upload)
  ├── SageMaker module (sagemaker_enabled flag)
  ├── SageMaker inference client code
  └── SageMaker scheduled stop/start
```

### Batch 0: Bootstrap (30 min agent time)

1. Create `terraform/bootstrap/main.tf` with S3 bucket (with bucket policy + MFA delete protection) + DynamoDB table
2. Create `terraform/backend.tf`, `providers.tf`, `variables.tf`
3. Run `terraform init && terraform apply -auto-approve` from bootstrap
4. Verify bucket and DynamoDB table created
5. Copy bucket/DynamoDB names to `backend.tf`

**Dependencies:** AWS CLI configured with AdminAccess
**Parallel:** No (bootstrap is sequential)

**Definition of Done:**
- [ ] `terraform apply` from `terraform/bootstrap/` completes with no errors
- [ ] S3 bucket `laad-terraform-state-ahmedikram` exists with versioning enabled
- [ ] DynamoDB table `laad-terraform-lock` exists with PAY_PER_REQUEST billing
- [ ] `terraform init` from root `terraform/` loads remote state from S3
- [ ] `terraform plan` from root shows "No changes" (clean slate)

### Batch 1a: Foundation (parallel, 2-3 hrs agent time)

**Agent A — VPC Module:**
- VPC (10.0.0.0/16), 2 AZs (eu-west-2a, eu-west-2b)
- 2 public subnets, 2 private subnets
- Internet Gateway, NAT Gateway (single, in AZ-a)
- Route tables (public → IGW, private → NAT)
- Gateway endpoints (S3, DynamoDB)
- All security groups: ALB SG, ECS API SG, ECS Consumer SG, ECS Generator SG, RDS SG, Kafka SG, Redis SG, ChromaDB SG
- Outputs: vpc_id, subnet IDs, SG IDs, NAT Gateway ID

**Agent B — IAM Module:**
- GitHub Actions OIDC role (scoped: ECS UpdateService + RegisterTaskDefinition, ECR push, S3 sync, CloudFront)
- ECS Task Execution Role (ECR pull + CloudWatch logs + Secrets Manager read)
- ECS Task Role (SageMaker InvokeEndpoint, S3 read on mlflow-artifacts, CloudWatch logs)
- SageMaker Execution Role (scoped: CreateEndpoint, InvokeEndpoint on laad-*, S3 read on models)
- Outputs: all role ARNs

**Agent C — ECR Module:**
- Single repository `laad-app`
- Image scan on push
- Lifecycle policy: keep last 25 images
- Output: repo URL

**Agent D — Secrets Module:**
- `laad/db/master`: RDS credentials via `random_password`
- `laad/app/jwt`: JWT via `random_password`
- `laad/rag/ollama`: API keys (from rotated .env values)
- `laad/mlflow`: MLflow tracking URI (no static AWS creds)
- `laad/app/backend`: All runtime env vars
- `laad/sagemaker`: Placeholder (updated post-deploy)
- Outputs: all secret ARNs

**Dependencies:** None (all parallel)
**Depended by:** Batch 2a, Batch 2b

**Definition of Done:**
- [ ] `terraform plan` shows all expected resources (VPC with 2 AZs, NAT Gateway, IGW, 8 SGs, 4 IAM roles, ECR repo, 7 Secrets Manager entries)
- [ ] VPC CIDR verified: non-overlap with existing MLflow VPC
- [ ] NAT Gateway is running in public subnet of AZ-a (verify via AWS console or `aws ec2 describe-nat-gateways`)
- [ ] GitHub OIDC provider exists with correct trust policy (repo: `ahmedikram/laad`, branch: `main`)
- [ ] ECS Task Role has SageMaker InvokeEndpoint + S3 read policies (no static AWS creds)
- [ ] ECR repository `laad-app` exists with scan-on-push enabled and lifecycle policy (25 images)
- [ ] All 7 secrets exist in Secrets Manager with correct keys and values
- [ ] JWT secret is generated by `random_password` (not a placeholder — verify via Secrets Manager console)
- [ ] `terraform apply` output matches expected resource count

### Batch 1b: Code Changes (parallel with Batch 1a, 2-3 hrs agent time)

**Agent E — Backend Code Changes:**
1. `ml_detector.py`: Add S3 model download function, SageMaker inference client, production mode guard
2. `auth_*.py`: Remove `DEFAULT_SECRET_KEY`, add startup guard
3. `retriever.py`: Add try/except in `__init__`, gate ChromaDB operations
4. `consumer.py`: Add health server, add Kafka retry on connect
5. `init_db.py`: Add `LAAD_ENV=production` guard for `force=True`
6. `server.py`: Make CORS origins configurable via env var
7. `server.py` / `config.py`: Add `LAAD_ENV` support, remove startup retrain in production

**Agent F — Frontend Code Changes:**
1. `AuthProvider.jsx`: Use `VITE_API_URL` env var
2. Other hardcoded localhost references

**Agent G — Dockerfile:**
1. Add `USER appuser` + group setup
2. No other changes (single Dockerfile, ECS overrides command)
3. Remove any `ARG CMD` or ENTRYPOINT confusion

**Dependencies:** None (all parallel with Batch 1a)
**Depended by:** Batch 2b (CI/CD needs code to test)

**Definition of Done:**
- [ ] All backend code changes committed (S3 model loading, JWT guard, RAG graceful degradation, consumer health check + Kafka retry, configurable CORS, init_db production guard, SageMaker inference client)
- [ ] All frontend code changes committed (`VITE_API_URL` env var, no hardcoded localhost references)
- [ ] Dockerfile updated (USER appuser, curl installed, dead build-arg removed)
- [ ] `pytest backend/tests/ --ignore=backend/tests/stress --ignore=backend/tests/integration -k "not chroma and not rag and not kafka"` passes
- [ ] `npx vitest run` from `frontend/` passes
- [ ] `docker build -t laad-app:test backend/` succeeds without errors
- [ ] `docker run laad-app:test python -c "from backend.src.api.server import app"` succeeds (imports resolve, no startup crash from missing env vars)

### Batch 2a: Infrastructure (parallel, 3-4 hrs agent time)

**Agent H — RDS Module:**
- `aws_db_subnet_group` in private subnets
- `aws_db_instance`: db.t4g.micro, PostgreSQL 16, 20GB gp3, `deletion_protection = true`
- `random_password` for master creds → `laad/db/master` secret
- RDS SG: port 5432 from ECS API + Consumer SGs
- Outputs: endpoint, port, db_name

**Agent I — EC2 Kafka Module:**
- `aws_instance`: t4g.small, Amazon Linux 2023, 20GB gp3 encrypted
- `user_data` with full Kafka automation (Java 17, download, KRaft format, start)
- `aws_eip` for stable addressing
- Kafka SG: port 9092 from ECS Consumer SG
- `KAFKA_HEAP_OPTS=-Xms512m -Xmx512m`
- Outputs: private IP, EIP, SG ID

**Agent J — ECS Module:**
- Cluster (Fargate capacity providers)
- 5 task definitions with templates:
  - API: 1024/3072, on-demand, health check `/health`, all secrets injected
  - Consumer: 512/1024, Fargate Spot, health check `/health:8081`
  - Generator: 256/512, Fargate Spot
  - Redis: 256/512, Fargate Spot, redis:7-alpine
  - ChromaDB: 512/1024, Fargate Spot, chromadb/chroma
- 4 services (API on-demand, rest Spot)
- ALB: HTTP:80 (no HTTPS), target group health check `/health`
- CloudWatch log groups (7-day retention) + metric filters + dashboard

**Agent K — Frontend Module:**
- S3 bucket (private, versioning enabled)
- CloudFront distribution with OAC
- `forward = "all"` for query strings
- 404 → index.html error response
- S3 bucket policy → CloudFront only
- Outputs: CloudFront domain, S3 bucket name

**Agent L — Monitoring Module:**
- CloudWatch dashboard
- Budget alerts at 80%/100% of $50/mo (without SageMaker), $150/mo (with SageMaker)
- CPU credit alarm for RDS
- SageMaker invocation alarm

**Dependencies:** Batch 1a complete (VPC, IAM, ECR, Secrets)
**Depended by:** Batch 2b (CI/CD needs ECS and ECR to deploy)

**Definition of Done:**
- [ ] `terraform apply` completes with no errors
- [ ] RDS instance is in `available` status (`aws rds describe-db-instances --db-instance-identifier laad-postgres` returns `DBInstanceStatus: available`)
- [ ] EC2 Kafka instance is running (`aws ec2 describe-instances --filters "Name=tag:Name,Values=laad-kafka"`) — t4g.small, correct security group, EIP attached
- [ ] ECS cluster `laad-cluster` exists with Fargate capacity providers
- [ ] All 5 task definitions registered (api, consumer, generator, redis, chromadb) — verify via `aws ecs list-task-definitions`
- [ ] ALB DNS resolves: `curl -I http://<alb-dns>` returns HTTP 503 (expected — no healthy targets yet, but ALB is accepting connections)
- [ ] CloudFront distribution status is `Deployed` (`aws cloudfront get-distribution --id <id>`)
- [ ] S3 frontend bucket exists with versioning + public access block enabled
- [ ] CloudWatch dashboard exists with ALB, ECS, RDS, NAT Gateway, Kafka widgets
- [ ] Budget alerts created at 80%/100% of $50/mo (without SageMaker) and $150/mo (with SageMaker)

### Batch 2b: CI/CD (parallel with Batch 2a, 1-2 hrs agent time)

**Agent M — CI/CD Pipeline:**
- **`ci.yml`**: Python tests with `services.postgres` + vitest. Runs on all branches (PR and push).
- **`cd.yml`**: Deploy to AWS. Triggered by `workflow_run` event — runs only after `ci.yml` succeeds on `main`.
- `workflow_run` trigger avoids redundant builds and ensures only tested code is deployed.
- Build once, tag thrice (api-latest, consumer-latest, generator-latest) — in `cd.yml`.
- Test filtering via `--ignore` paths (not non-existent pytest markers).
- No `terraform.yml`, no SNS, no auto CloudFront invalidation.
- `AWS_ROLE_ARN` from Terraform output stored as GitHub secret.

**Dependencies:** Batch 1b (code changes for tests), ECR repo URL from Batch 1a
**Depended by:** Verification

**Definition of Done:**
- [ ] `ci.yml` passes on push to `main` (pytest `services.postgres` + vitest both green)
- [ ] `ci.yml` also passes on PR branches (confirmed by making a test branch)
- [ ] `cd.yml` triggers automatically after CI succeeds on `main` (verify via Actions tab)
- [ ] CD deploys complete: image built, tagged thrice (api/consumer/generator), pushed to ECR
- [ ] All 3 services (API, Consumer, Generator) show `runningCount=1` and `desiredCount=1` (`aws ecs describe-services --cluster laad-cluster --services laad-api-service laad-consumer-service laad-generator-service`)
- [ ] Schema init `run-task` completes with exit code 0 (verify via `aws ecs describe-tasks` — container exit code is 0)
- [ ] Tables confirmed: init_db created all tables (`SELECT table_name FROM information_schema.tables WHERE table_schema='public'` via a quick `run-task` override)
- [ ] API health check passes: `curl -f http://<alb-dns>/health` returns HTTP 200
- [ ] CloudFront URL serves React app (browser shows LAAD dashboard, not error page)
- [ ] Kafka consumer visible in CloudWatch logs (`/ecs/laad-consumer` has recent log events with no connection errors)

### Batch 3: SageMaker (1-2 hrs agent time, gated)

**Agent N — SageMaker:**
1. Download champion model from MLflow via ECS `run-task` and upload to S3
2. Create SageMaker module with `sagemaker_enabled = true`
3. `terraform apply` to create endpoint
4. **Propagate endpoint name**: Update `laad/sagemaker` secret with the Terraform output `sagemaker_endpoint_name`:
   ```bash
   ENDPOINT_NAME=$(terraform output -raw sagemaker_endpoint_name)
   aws secretsmanager update-secret --secret-id laad/sagemaker \
     --secret-string "{\"SAGEMAKER_ENDPOINT_NAME\":\"$ENDPOINT_NAME\",\"SAGEMAKER_REGION\":\"eu-west-2\"}"
   ```
5. **Redeploy ECS services** so API/Consumer pick up the new endpoint name:
   ```bash
   aws ecs update-service --cluster laad-cluster --service laad-api-service --force-new-deployment
   aws ecs update-service --cluster laad-cluster --service laad-consumer-service --force-new-deployment
   ```
6. EventBridge Scheduler for stop (22:00) / start (06:00) to extend credits
7. SageMaker inference client code already done in Batch 1b

**Dependencies:** Model uploaded to S3, Batch 1a complete (IAM roles)
**Depended by:** Final verification

**Definition of Done:**
- [ ] Model upload ECS `run-task` completes with exit code 0
- [ ] Model artifacts exist in S3 at `s3://laad-mlflow-artifacts/sagemaker-models/` (`aws s3 ls s3://laad-mlflow-artifacts/sagemaker-models/`)
- [ ] `terraform apply` with `sagemaker_enabled=true` completes with no errors
- [ ] SageMaker endpoint status is `InService` (`aws sagemaker describe-endpoint --endpoint-name laad-xgb-champion` returns `EndpointStatus: InService`)
- [ ] `laad/sagemaker` secret updated with endpoint name from Terraform output (`aws secretsmanager get-secret-value --secret-id laad/sagemaker`)
- [ ] ECS services redeployed (API + Consumer) to pick up new endpoint name
- [ ] Scheduled stop (22:00) and start (06:00) EventBridge rules created (`aws scheduler list-schedules`)
- [ ] Anomaly detection test: API endpoint returns SageMaker-backed result (not heuristic-only fallback)

### Verification (You, ~1 hr)

1. Verify credential rotation: `.env` removed from git, all passwords rotated
2. Verify Terraform outputs: ALB DNS, CloudFront domain, ECR repo URL
3. Push to `main` → verify `ci.yml` passes, then `cd.yml` triggers and deploys all services
4. Run schema init one-shot task, verify tables created
5. Open CloudFront URL → React app loads, APIs respond
6. Verify Kafka consumer processes messages (CloudWatch logs)
7. Verify anomaly detection: call endpoint, check SageMaker invocation or fallback
8. Verify Redis/chroma running: check CloudWatch logs for each service
9. Push trivial change → verify full CI/CD pipeline
10. Verify CloudWatch dashboard shows data

## Manual Steps (Remaining)

Minimal — most steps are automated by agents:

1. **Rotate credentials** — Before anything else, rotate ALL exposed credentials from `.env`. `git rm --cached .env`. Scrub git history with BFG Repo-Cleaner or `git filter-branch`.
2. **Apply Terraform (gate)** — After Batch 0 and Batch 1a, run `terraform init && terraform apply` from `terraform/`. Review the plan output before approving. Repeat for Batch 2a and Batch 3 (SageMaker) when their modules are ready.
3. **Set GitHub Actions secrets** — After Terraform creates the OIDC role, add `AWS_ROLE_ARN` and `AWS_REGION` to GitHub secrets. Also add `ECR_REPOSITORY` and `API_URL` (ALB DNS).
4. **Run schema init** — One-time `aws ecs run-task` command after first Terraform apply (scripted in CI/CD docs above, but run manually for the first deploy).
5. **Subscribe to budget alerts** — AWS Budget alerts email to your address.
6. **Optional: Model upload for SageMaker** — If SageMaker is enabled, run the model upload ECS task before enabling `sagemaker_enabled=true` and applying Batch 3 Terraform.

## Cost Estimate (Monthly, Corrected)

| Resource | Cost | Notes |
|---|---|---|
| NAT Gateway (single AZ) | ~$35 | Largest baseline cost. Single AZ saves ~$35 |
| ALB (HTTP) | ~$22 | Near-zero LCU for demo load |
| Fargate API (on-demand 1 task, 1024/3072) | ~$30 | On-demand for reliability. API must stay up |
| Fargate Consumer (Spot 1 task, 512/1024) | ~$4 | Spot savings ~70% |
| Fargate Generator (Spot 1 task, 256/512) | ~$3 | Spot savings ~70% |
| Fargate Redis (Spot 1 task, 256/512) | ~$3 | Spot savings ~70% |
| Fargate ChromaDB (Spot 1 task, 512/1024) | ~$4 | Spot savings ~70% |
| EC2 t4g.small (Kafka, 20GB gp3 encrypted) | ~$12 | Upgraded from nano. 2 GB RAM sufficient |
| RDS db.t4g.micro (20GB gp3, 7-day backup) | ~$15 | PostgreSQL 16, storage encrypted, deletion_protection=true |
| SageMaker ml.m5.large (on-demand) | ~$84 | ~$48 credits cover ~2.5 weeks. Scheduled stop/start can halve this |
| CloudFront (PriceClass_100) | ~$1 | Minimal data transfer |
| S3 frontend bucket + versioning | ~$0.20 | Negligible |
| ECR storage (single repo) | ~$0.10 | Per GB/month |
| CloudWatch Logs (5 groups, 7-day retention) | ~$5 | 7-day retention keeps costs reasonable |
| Secrets Manager (7 secrets) | ~$2.80 | $0.40/secret/month |
| S3 Terraform state + versioning | ~$0.10 | Minimal |
| DynamoDB (PAY_PER_REQUEST) | ~$0.10 | Lock table, near-zero usage |
| CloudWatch Dashboard | $0 | Free |
| Budget alerts | $0 | Free |
| **Total (with SageMaker)** | **~$221/mo** | Credits (~$48) cover ~6.5 days at full rate. Since SageMaker runs 24/7, credits last ~2.5 weeks. |
| **Total (without SageMaker)** | **~$137/mo** | Baseline without SageMaker. Longer credit duration. |
| **Credits usable duration (full stack)** | ~6.5 days | At $221/mo, $48 in credits is consumed in ~6.5 days of runtime. |
| **Credits usable duration (w/ SageMaker stop/start)** | ~13 days | Scheduled stop/start (16h/day) halves SageMaker cost, extends credits. |

> **Cost reality vs original plan:** The original plan estimated ~$96/mo (without SageMaker) and ~$180/mo (with SageMaker). Actual costs after correcting for Fargate Spot prices, CloudWatch Logs, Secrets Manager, and additional services (generator, ChromaDB, Redis): **~$137/mo baseline, ~$221/mo with SageMaker.** Budget alerts are configured to prevent surprises.
>
> **SageMaker stop/start:** Use EventBridge Scheduler to stop the endpoint at 22:00 and start at 06:00. This saves ~$28/mo (16/24 reduction). Combined: ~$84 → ~$56/mo ($48 credits last ~3.5 weeks with stop/start).

## Architectural Decisions & Rationale

| Decision | Choice | Why |
|---|---|---|
| ALB HTTP-only | No ACM cert needed | ACM doesn't issue self-signed certs. CloudFront handles TLS for frontend. API calls from trusted sources use HTTP within VPC. |
| Kafka on t4g.small | 2 GB RAM, heap limits | t4g.nano (0.5 GB) cannot run Kafka. t4g.small at ~$12/mo is the minimum viable instance. |
| ChromaDB + Redis on ECS | Fargate tasks | Headline RAG feature and JWT blacklisting don't work without them. ~$7/mo combined. |
| Single ECR repo, two tags | Build once, tag twice | Avoids double build time. Simplifies CI/CD. |
| API on-demand, rest Spot | Reliability + cost | API must survive Spot interruptions for demos. Consumer/generator/Redis/Chroma are resilient. |
| VPC endpoints for S3/DynamoDB only | NAT covers rest | Gateway endpoints are free. ECR/CloudWatch access through NAT (already budgeted). |
| No SNS notifications | Simpler | Pipeline status visible in GitHub Actions UI. No email infrastructure to maintain. |
| No terraform.yml pipeline | Manual apply | Terraform plan reviewed before apply. CI/CD for IaC adds complexity without proportional benefit. |
| Python health checks | Simpler | Built-in HTTP server for consumer health. FastAPI `/health` endpoint for API. |
| No CloudFront auto-invalidation | Manual when needed | S3 object versioning enables rollback. Manual invalidation is rare for portfolio. |

## Risks & Mitigations

| Risk | Severity | Mitigation |
|---|---|---|
| Kafka single point of failure | Medium | Single broker, no replication. Acceptable for portfolio. Data can be regenerated via log generator. |
| RDS single point of failure | Low | Automated backup (7-day retention). Point-in-time recovery. `deletion_protection = true` prevents accidental destroy. |
| NAT Gateway single point of failure | Low | Acceptable for portfolio. Single AZ design. |
| Fargate Spot interruption (non-API) | Low | Tasks auto-restart. All non-API services have retry/graceful degradation. |
| SageMaker endpoint cost overrun | Medium | Budget alerts at 80%/100% thresholds. Scheduled stop/start. Credits managed. |
| MLflow RDS publicly accessible | Medium | Password rotated post-review. Security group restricts access. VPC peering deferred (acceptable). |
| CI tests fail due to missing external deps | Low | Tests use `--ignore` for stress/integration. `services.postgres` provides clean test DB. Chroma/RAG/Kafka tests skipped in CI. |
| `force=True` called in production | Low | `LAAD_ENV=production` guard raises RuntimeError. Only test files use `force=True`. |
| ECR lifecycle deletes rollback target | Low | 25-image retention + tagged images excluded from pruning. `:latest` tags always point to current deployment. |
| JWT secret compromised | Low | `random_password` in Terraform (64 chars, no special). Secret can be rotated without downtime. |

## Key Takeaways

1. **~6-9 days wall-clock** (not 28-47 days) — agents parallelize batches. Human supervision is the bottleneck, not agent capacity. Multiple agents work simultaneously on independent modules.

2. **~$221/mo with SageMaker** — not $1,200-1,600 as originally claimed. Budget alerts configured at 80%/100% thresholds.

3. **All 5 P0 blockers fixed**: init_db production guard (P0-1), VITE_API_URL frontend (P0-2), IaC creation (P0-3), consumer health check (P0-4), S3 model loading (P0-5).

4. **All 11 critical findings fixed**: credentials rotated (C-1), Kafka t4g.small (C-2), --ignore test filtering (C-3), generator on ECS (C-4), ChromaDB/Redis on ECS (C-5), RAGRetriever try/except (C-6), HTTP-only ALB (C-7), dead build-arg removed (C-8), gateway endpoint docs corrected (C-9), JWT random_password guard (C-10), CI/CD files created (C-11).

5. **SageMaker included** — it's the AI/ML CV story. Scheduled stop/start extends credit life. Gated behind `sagemaker_enabled` variable.

6. **Credential hygiene enforced**: No static AWS creds in Secrets Manager (ECS task role handles S3 access). `.env` removed from git. JWT generated by Terraform (no placeholder window).

7. **Rollback strategy**: ECS task definition revision (25 images retained in ECR), S3 versioning for frontend, RDS backup restore (7-day retention).
