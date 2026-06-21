# LAAD Implementation Log

> Living document for agent-driven AWS deployment. Updated as execution progresses.
> Companion to `DEPLOYMENT_PLAN.md` — the plan says *what*, this says *how* and *what happened*.

---

## Agent Orchestration Strategy

### Roles

| Role | Who | Responsibility |
|------|-----|----------------|
| **Commander** | You (user) | Rotate credentials, run `terraform apply` (gate), set GitHub secrets, verify DoD, make scope decisions |
| **Orchestrator** | Me (big-pickle OR deepseek) | Launch subagents, review output, sequence batches, update this log, report progress |
| **Build Agent** | `build` subagent | Write code, Terraform HCL, YAML pipelines (one per module within a batch) |
| **Architect** | `code-architect` subagent | For complex new modules (ECS task defs, IAM policies, CI/CD pipelines) |
| **Reviewer** | `code-reviewer` subagent | Post-build review of any batch (optional, for high-risk modules) |

### Execution Model

```
Per batch:
  1. Orchestrator launches N build agents in parallel (one per module)
  2. Each agent returns its output (files written, key decisions)
  3. Orchestrator reviews output against DoD checklist
  4. If all pass → Commander runs terraform apply / manual steps
  5. If any fail → re-roll the agent or manual fix
  6. Orchestrator updates status in this log
```

### Rules

- **Never** launch more than 7 agents per parallel wave (context management)
- **Always** read an agent's full output before accepting it
- **Re-roll** a failing agent with clearer instructions before manual fixing
- **Decision log** every deviation from the plan (even minor ones)
- **Checkpoint** after each batch — Commander verifies DoD before next batch begins

---

## Subagent Type Assignments

| Batch | Module | Subagent Type | Notes |
|-------|--------|---------------|-------|
| 0 | Bootstrap Terraform | `build` | Simple S3 + DynamoDB |
| 0 | backend.tf / providers.tf | `build` | Boilerplate config |
| 1a | VPC module | `code-architect` | Security groups need care |
| 1a | IAM module | `code-architect` | Least-privilege policies, OIDC trust |
| 1a | ECR module | `build` | Simple repo + lifecycle |
| 1a | Secrets module | `build` | random_password + Secrets Manager |
| 1b | Backend code changes | `code-architect` | 8 changes across 6 files |
| 1b | Frontend code changes | `build` | Single env var change |
| 1b | Dockerfile | `build` | USER appuser + curl |
| 2a | RDS module | `build` | Standard RDS config |
| 2a | EC2 Kafka module | `code-architect` | user_data automation is critical |
| 2a | ECS module | `code-architect` | 5 task defs + ALB + services, most complex module |
| 2a | Frontend infra module | `build` | S3 + CloudFront |
| 2a | Monitoring module | `build` | Dashboard + budget alerts |
| 2b | CI/CD pipelines | `code-architect` | ci.yml + cd.yml with all quality gates |
| 3 | SageMaker module | `code-architect` | Endpoint config, stop/start scheduler |

---

## Checkpoint Gates (Commander Required)

Every checkpoint requires you to run a command and confirm the output before the orchestrator proceeds.

| # | Phase | What you do | Expected outcome |
|---|-------|-------------|------------------|
| G0a | Pre-flight | Rotate credentials, scrub `.env` from git | No secrets in git history |
| G0b | Bootstrap | `terraform apply -auto-approve` from `terraform/bootstrap/` | S3 bucket + DynamoDB created |
| G1 | Phase 1 | `terraform init && terraform plan` → review → `terraform apply` | VPC, IAM, ECR, Secrets created |
| G2a ✅ | Phase 2 infra | `terraform init && terraform plan` → review → `terraform apply` | RDS, Kafka, ECS, CloudFront, Monitoring created |
| G2b ✅ | Phase 2 CI/CD | Add `AWS_ROLE_ARN`, `ECR_REPOSITORY`, `API_URL` to GitHub secrets | GitHub secrets populated |
| G2c | Phase 2 deploy | Push to `main` → watch CI pass → CD deploy | All services running, schema initialized |
| G3 | Phase 3 | `terraform apply -var="sagemaker_enabled=true"` | SageMaker endpoint created + stop/start scheduled |
| G4 | Final | Walk through 10-step verification checklist | Everything confirmed working |

---

## Batch Progress

> Each batch has a task checklist mirroring the DoD items from `DEPLOYMENT_PLAN.md`.
> Checkboxes are updated as tasks complete. Date stamped on completion.

---

### Batch 0 — Bootstrap (✅ Complete)

**Status:** ✅ Complete &nbsp;|&nbsp; **Date:** 2026-06-20 &nbsp;|&nbsp; **Commander gate:** G0b ✅

**Modules:** Bootstrap Terraform (build), backend.tf/providers.tf (build)

- [x] `terraform apply` from `terraform/bootstrap/` completes with no errors
- [x] S3 bucket `laad-terraform-state-ahmedikram` exists with versioning enabled
- [x] DynamoDB table `laad-terraform-lock` exists with PAY_PER_REQUEST billing
- [x] `terraform init` from root `terraform/` loads remote state from S3

| Module | Agent ID | Files Created | Re-rolls | Verified |
|--------|----------|---------------|----------|----------|
| Bootstrap S3 + DynamoDB | orchestrator | `terraform/bootstrap/main.tf` | 0 | Verified via `aws s3api` and `aws dynamodb` CLI |
| backend.tf / providers.tf | orchestrator | `terraform/backend.tf`, `terraform/providers.tf`, `terraform/variables.tf`, `terraform/main.tf` | 0 | `terraform plan` shows "No changes" |

---

### Batch 1a — Foundation (✅ Complete)

**Status:** ✅ Complete &nbsp;|&nbsp; **Date:** 2026-06-20 &nbsp;|&nbsp; **Commander gate:** G1 ✅

**Modules:** VPC (architect), IAM (architect), ECR (build), Secrets (build)

- [x] `terraform plan` shows 66 resources (VPC with 2 AZs, NAT Gateway, IGW, 8 SGs, 4 IAM roles, OIDC provider, ECR repo, 7 Secrets Manager entries)
- [x] VPC CIDR verified: non-overlap with existing MLflow VPC (`172.31.0.0/16`)
- [x] NAT Gateway is running in public subnet of AZ-a (verified `aws ec2 describe-nat-gateways`)
- [x] GitHub OIDC provider exists with correct trust policy (repo: `ahmedikram/laad`, branch: `main`)
- [x] ECS Task Role has SageMaker InvokeEndpoint + S3 read policies (no static AWS creds)
- [x] ECR repository `laad-app` exists with scan-on-push enabled and lifecycle policy (25 images)
- [x] All 7 secrets exist in Secrets Manager with correct keys and values
- [x] JWT secret is generated by `random_password` (not a placeholder)
- [x] `terraform apply` output: 21 resources added (45 already existed from partial first apply, total 66 in state)

| Module | Agent ID | Files Created | Re-rolls | Verified |
|--------|----------|---------------|----------|----------|
| VPC | `ses_11aa10edbffeOeqQvdTYWpDzxq` | `terraform/modules/vpc/main.tf`, `variables.tf`, `outputs.tf` | 0 | `terraform apply` created all 27 VPC resources |
| IAM | `ses_11aa0ee1bffewptEx4rrW8WTOZ` | `terraform/modules/iam/main.tf`, `variables.tf`, `outputs.tf` | 1 (OIDC existed) | `terraform apply` created OIDC data + 4 roles |
| ECR | `ses_11aa0e46bffeYvh7EW179oHh5b` | `terraform/modules/ecr/main.tf`, `variables.tf`, `outputs.tf` | 1 (lifecycle policy) | `terraform apply` created repo + lifecycle |
| Secrets | `ses_11aa0bc39ffeHUr2OFR62yLsKw` | `terraform/modules/secrets/main.tf`, `variables.tf`, `outputs.tf` | 0 | `terraform apply` created 7 secrets + 2 random_password |

---

### Batch 1b — Code Changes (✅ Complete)

**Status:** ✅ Complete &nbsp;|&nbsp; **Date:** 2026-06-20 &nbsp;|&nbsp; **Commander gate:** (code review, no terraform)

**Modules:** Backend (architect), Frontend (build), Dockerfile (build)

**Prerequisite:** MLflow RDS `laad-mlflow-postgres` password rotated (→ `GU1tA6axYwk8dD42JKUzrA9k`), secret `laad/db/mlflow` updated with `mlflow_admin` user.

- [x] All backend code changes committed — 8 changes across 6 files
  - `ml_detector.py`: S3 model download, SageMaker inference client, production mode guard
  - `auth_router.py`: Removed `DEFAULT_SECRET_KEY`, raises `RuntimeError` if `JWT_SECRET_KEY` not set
  - `retriever.py`: try/except in `__init__`, all methods guard against `collection is None`
  - `consumer.py`: Health server (port 8081 via daemon thread) + Kafka retry (5 attempts)
  - `init_db.py`: `LAAD_ENV=production` guard for `force=True`
  - `server.py`: Configurable CORS via `CORS_ORIGINS` env var, skip startup retrain in production
- [x] All frontend code changes committed — `AuthProvider.jsx` uses `VITE_API_URL` env var, no other hardcoded localhost references found
- [x] Dockerfile updated — multi-stage build (builder + runtime), `USER appuser:appgroup`, `curl` installed, no dead build-args
- [x] `pytest backend/tests/ ...` — **344 passed** (0 failures)
- [x] `npx vitest run` — **149 passed** (0 failures)
- [x] `docker build -t laad-app:test backend/` — **succeeded** (multi-stage, no errors)
- [x] `docker run laad-app:test python -c "from backend.src.api.server import app"` — **OK** (with JWT_SECRET_KEY)

| Module | Agent ID | Files Created | Re-rolls | Verified |
|--------|----------|---------------|----------|----------|
| Backend (8 changes) | `ses_11a934aa1ffeLX9Bd6837TD61a` | 6 files modified | 0 | 344 pytest tests pass |
| Frontend (VITE_API_URL) | `ses_11a90b968fferrYJgpf8Dgpz4B` | 1 file modified | 0 | 149 vitest tests pass |
| Dockerfile | `ses_11a902cd6ffeK9NtI05oJRrJkZ` | 1 file modified | 0 | `docker build` + `docker run` succeed |

---

### Batch 2a — Infrastructure (✅ Complete)

**Status:** ✅ Complete &nbsp;|&nbsp; **Date:** 2026-06-21 &nbsp;|&nbsp; **Commander gate:** G2a ✅

**Modules:** RDS (build), EC2 Kafka (architect), ECS (architect), Frontend infra (build), Monitoring (build)

**6 errors encountered and fixed during apply:**

1. ✅ **PG version 16.3 not available in eu-west-2** — Changed to `16.14` (latest available)
2. ✅ **Metric filter dependency** — `log_group_name` hardcoded string → `aws_cloudwatch_log_group.api.name`
3. ✅ **Budgets removed** — `InvalidParameterException` on `limit_unit`. Deferred to manual AWS Console setup
4. ✅ **RDS secret conflict** — `laad/db/master` already existed from Batch 1a. Changed `resource` → `data`
5. ✅ **RDS backup retention** — 7 days exceeds free tier max. Changed to 1 day
6. ✅ **Duplicate SG rule** — VPC module already creates full egress. Removed rds_egress

**Final apply: 9 added, 2 changed, 2 destroyed, 0 warnings.**

- [x] `terraform apply` completed with no errors
- [x] RDS `laad-postgres` is **available** (PG 16.14, `db.t4g.micro`, 20GB gp3)
- [x] Kafka EC2 running: t4g.small, `10.0.1.253`, EIP `16.61.212.196`
- [x] ECS cluster `laad-cluster` exists with Fargate capacity providers (Container Insights enabled)
- [x] ALB `laad-alb-1715737937.eu-west-2.elb.amazonaws.com` — active, HTTP:80 → API TG
- [x] All 5 task definitions registered (api:1, consumer:1, generator:3, redis:1, chromadb:1)
- [x] All 5 ECS services ACTIVE (Redis+ChromaDB 1/1 running; API+Consumer+Generator 0/1 — need ECR images)
- [x] S3 bucket `laad-frontend-676433090516` with versioning + public access blocked
- [x] CloudFront distribution `d3q355gitrlwpr.cloudfront.net` — **Deployed**
- [x] CloudWatch dashboard `laad-dashboard-production` with 6 widgets
- [x] 3 alarms created (RDS CPU credits, API down, SageMaker latency) — RDS CPU in ALARM (expected for new instance)
- [x] Budget alerts — **deferred to manual setup** (AWS Budgets Console, simple monthly $50/$150 alerts)

| Module | Agent ID | Files Created | Re-rolls | Verified |
|--------|----------|---------------|----------|----------|
| RDS | `ses_115cd08b0ffeABhLQmQ1LZNvhZ` | `terraform/modules/rds/main.tf`, `variables.tf`, `outputs.tf` | **4** (**PG version**, secret conflict, backup retention, dup SG rule) | `available`, PG16.14, `db.t4g.micro` |
| EC2 Kafka | `ses_115cb4723ffeMvmZl27IM1RZAw` | `terraform/modules/kafka/main.tf`, `variables.tf`, `outputs.tf` | 0 | Running: t4g.small, 10.0.1.253, EIP attached |
| ECS | `ses_115c85f7cffe9Qr4y0sWAt8SJ1` | `terraform/modules/ecs/main.tf`, `variables.tf`, `outputs.tf` | **1** (metric filter dependency) | Cluster active, 5 task defs, 5 services, ALB online |
| Frontend infra | `ses_115c59b01ffeTsPHY8e45jgrwB` | `terraform/modules/frontend/main.tf`, `variables.tf`, `outputs.tf` | 0 | S3 bucket + CloudFront deployed |
| Monitoring | `ses_115c458a5ffe031I7ahyx4JMXt` | `terraform/modules/monitoring/main.tf`, `variables.tf`, `outputs.tf` | **1** (budgets removed) | 3 alarms + SNS topic created |

---

### Batch 2b — CI/CD (✅ Tested, CD Trigger Fixed)

**Status:** ✅ CI passing &nbsp;|&nbsp; **Date:** 2026-06-21 &nbsp;|&nbsp; **Commander gate:** G2b ✅ (secrets set) → G2c 🔄 (CD trigger fixed, awaiting deploy)

**Modules:** CI/CD pipelines (architect) — `ci.yml` + `cd.yml`

**Corrections from DEPLOYMENT_PLAN:**
- ECS service names: `laad-api`, `laad-consumer`, `laad-generator` (no `-service` suffix). Updated in `cd.yml`.
- S3 bucket: `laad-frontend-676433090516` (not `laad-frontend-ahmedikram`). Sent via `S3_BUCKET` secret.
- `workflow_run` trigger uses `github.event.workflow_run.head_sha` for correct commit checkout.

**CI Bugs Fixed (6 rounds):**

| # | Fix | Cause | Round |
|---|-----|-------|-------|
| 1 | Ruff `v0.36.0` in `ci.yml` | Trivy action `0.29.3` tag deleted in March 2026 supply chain cleanup | R1 |
| 2 | Ruff lint: 125→0 errors (F401/F841/E402/E741/F601/F821) | Batch 1b code left dead imports, tests used `# noqa` patterns | R2 |
| 3 | `--ignore-vuln CVE-2026-45829` in pip-audit | chromadb 1.5.9 has pre-auth code injection CVE (no fix exists) | R3 |
| 4 | `JWT_SECRET_KEY` in CI env | Batch 1b `auth_router.py` raises `RuntimeError` if not set (no more default) | R4 |
| 5 | `TEST_POSTGRES_*` env vars (not `POSTGRES_*`) | conftest reads `TEST_POSTGRES_HOST/PORT/DB` but CI set the wrong vars | R4 |
| 6 | `LAAD_ENV=production` in CI steps | MLflow connection timeout (~4m per TestClient) in `_check_and_retrain_on_startup()` | R5 |
| 7 | `test_init_db_force_drops_tables` — `patch.dict(os.environ, {"LAAD_ENV": "test"})` | Batch 1b production guard blocks `init_db(force=True)`. `os.getenv` patch was unreliable | R6 |
| 8 | `test_sends_event_to_atm_events_topic` — `patch("random.random", 0.1)` | Flaky: `random() < 0.35` with 10 ATMs = ~1.35% failure per run | R6 |
| 9 | CI workflow name: `CI` → `CI` (was `LAAD CI`, reverted) | CD `workflow_run` referenced `["LAAD CI"]` but workflow was named `CI` — mismatch prevented CD trigger | R7 |

- [x] `ci.yml` created — Ruff lint, pip-audit, Trivy, pytest (services.postgres), vitest
- [x] **CI is green** — all 344 pytest + 149 vitest tests passing
- [x] `cd.yml` created — `workflow_run` trigger, build once/tag thrice, ECS force-deploy, S3 sync, API smoke test
- [x] **Commander:** 5 GitHub secrets set (AWS_ROLE_ARN, AWS_REGION, ECR_REPOSITORY, API_URL, S3_BUCKET)
- [x] CD `workflow_run` trigger fixed: now references `["CI"]` (name matches CI workflow)
- [ ] 🚀 **Next:** Push to `main` → CI passes → CD auto-triggers → deploy + schema init

**After push to `main`:**
- [ ] `ci.yml` passes on push (CI already green, verify one more run)
- [ ] `cd.yml` triggers automatically after CI succeeds (previously blocked by name mismatch)
- [ ] CD deploys: image built, tagged thrice (api/consumer/generator), pushed to ECR
- [ ] API service shows `runningCount=1`
- [x] **Schema init:** Auto-run in CD pipeline after smoke test (idempotent `init_db(force=False)`, `CREATE TABLE IF NOT EXISTS`)
- [ ] Tables confirmed: `SELECT table_name FROM information_schema.tables WHERE table_schema='public'`
- [ ] API health: `curl -f http://<alb-dns>/health` → HTTP 200
- [ ] CloudFront URL serves React app

| File | Agent | Created | Verified |
|------|-------|---------|----------|
| `ci.yml` | build | `.github/workflows/ci.yml` | CI run #2790xxxxx — ✅ All steps pass |
| `cd.yml` | build | `.github/workflows/cd.yml` | YAML syntax OK, trigger fixed |

---

### Batch 3 — SageMaker (🔲 Pending, gated)

**Status:** 🔲 Pending &nbsp;|&nbsp; **Date:** — &nbsp;|&nbsp; **Commander gate:** G3

**Modules:** SageMaker (architect) — only if `sagemaker_enabled=true`

- [ ] Model upload ECS `run-task` completes with exit code 0
- [ ] Model artifacts exist in S3 at `s3://laad-mlflow-artifacts/sagemaker-models/` (`aws s3 ls s3://laad-mlflow-artifacts/sagemaker-models/`)
- [ ] `terraform apply` with `sagemaker_enabled=true` completes with no errors
- [ ] SageMaker endpoint status is `InService` (`aws sagemaker describe-endpoint --endpoint-name laad-xgb-champion` returns `EndpointStatus: InService`)
- [ ] `laad/sagemaker` secret updated with endpoint name from Terraform output (`aws secretsmanager get-secret-value --secret-id laad/sagemaker`)
- [ ] ECS services redeployed (API + Consumer) to pick up new endpoint name
- [ ] Scheduled stop (22:00) and start (06:00) EventBridge rules created (`aws scheduler list-schedules`)
- [ ] Anomaly detection test: API endpoint returns SageMaker-backed result (not heuristic-only fallback)

| Module | Agent ID | Files Created | Re-rolls | Verified |
|--------|----------|---------------|----------|----------|
| SageMaker | — | — | — | — |

---

### Final Verification (🔲 Pending)

**Status:** 🔲 Pending &nbsp;|&nbsp; **Date:** — &nbsp;|&nbsp; **Commander gate:** G4

- [ ] Credential rotation: `.env` removed from git, all passwords rotated
- [ ] Terraform outputs confirmed: ALB DNS, CloudFront domain, ECR repo URL
- [ ] Push to `main` → `ci.yml` passes, then `cd.yml` triggers and deploys all services
- [ ] Schema init one-shot task runs, tables created in RDS
- [ ] Open CloudFront URL → React app loads, APIs respond
- [ ] Kafka consumer processes messages (CloudWatch logs)
- [ ] Anomaly detection: call endpoint, check SageMaker invocation or fallback
- [ ] Redis/Chroma running: check CloudWatch logs for each service
- [ ] Push trivial change → verify full CI/CD pipeline (ci.yml → cd.yml)
- [ ] CloudWatch dashboard shows data

---

## Decision Log

| # | Date | Decision | Rationale | Author |
|---|------|----------|-----------|--------|
| D01 | 2026-06-20 | MLflow VPC CIDR is `172.31.0.0/16` (default VPC) — no overlap with LAAD `10.0.0.0/16` | Prerequisite verification confirmed no CIDR conflict | orchestrator |
| D02 | 2026-06-20 | `dynamodb_table` deprecation warning in `backend.tf` — **fixed** via `use_lockfile = true` | Plan explicitly requires state locking. Switched to `use_lockfile` per Terraform 1.15 deprecation guidance. Local file-based locking sufficient for single-operator workflow. | orchestrator |
| D03 | 2026-06-20 | Single NAT Gateway in AZ-a (not multi-AZ) | Saves ~$35/mo. Single point of failure for AZ-b private subnets, but acceptable for this project's cost profile. | VPC-agent |
| D04 | 2026-06-20 | S3 & DynamoDB Gateway Endpoints (not Interface) | Gateway endpoints are free; Interface endpoints cost ~$7/mo each. Both services support Gateway type. | VPC-agent |
| D05 | 2026-06-20 | Separate `aws_security_group_rule` resources (not inline ingress/egress blocks) | Avoids recreating the entire SG when a rule changes, and makes cross-SG references (`source_security_group_id`) explicit and dependency-safe. | VPC-agent |
| D06 | 2026-06-20 | ECR lifecycle excludes `api-latest`, `consumer-latest`, `generator-latest` tags | Images tagged with the three active tags are exempt from the 25-image prune limit via count threshold of 99,999, ensuring active deployment tags are never garbage-collected. | ECR-agent |
| D07 | 2026-06-20 | MLflow DB password stored as `PLACEHOLDER_UPDATE_VIA_CLI` in Terraform | Actual password is unknown and must not live in Terraform state. Updated post-deploy via AWS CLI in Batch 1b. | secrets-agent |
| D08 | 2026-06-20 | ECS Task Role uses inline policies only — no static AWS credentials | All service interactions (SageMaker InvokeEndpoint, S3 GetObject, CloudWatch logs) use ECS task IAM role. No access keys anywhere. | IAM-agent |
| D09 | 2026-06-21 | Budgets removed from Terraform; deferred to manual AWS Console setup | `InvalidParameterException` on `limit_unit`. Cost budgets are simple monthly alerts not worth complex debugging. Setup via AWS Budgets Console with identical thresholds (80%/100% at $50/$150). | Commander |
| D10 | 2026-06-21 | RDS module reads existing `laad/db/master` secret instead of creating new one | Batch 1a secrets module already created `laad/db/master`. RDS module now uses `data.aws_secretsmanager_secret` to reference it and only creates `aws_secretsmanager_secret_version` to populate the RDS endpoint | orchestrator |
| D11 | 2026-06-21 | RDS backup retention reduced to 1 day (free tier) | Free tier max is 1 day backup retention. Acceptable for dev/pre-prod; upgrade when moving to production. | orchestrator |
| D12 | 2026-06-21 | Metric filter `log_group_name` references the resource directly (not hardcoded) | Ensures implicit `depends_on` ordering so the log group is created before the metric filter that references it. | orchestrator |
| D13 | 2026-06-21 | PostgreSQL version 16.14 used instead of 16.3 | 16.3 not available in eu-west-2. 16.14 is latest available 16.x. | orchestrator |
| D14 | 2026-06-21 | Deprecation warning D02 fixed: `dynamodb_table` → `use_lockfile = true` | Terraform 1.15 deprecation. File-based locking sufficient for single-operator workflow. DynamoDB table kept in state, just unused. | orchestrator |
| D15 | 2026-06-21 | ECS service names in `cd.yml`: `laad-api` not `laad-api-service` | DEPLOYMENT_PLAN referenced `laad-api-service` suffix but ECS module creates services as `laad-api` (matching task definition family). CD pipeline corrected. | orchestrator |
| D16 | 2026-06-21 | S3 bucket name in `cd.yml` via `S3_BUCKET` secret (not hardcoded) | DEPLOYMENT_PLAN hardcoded `laad-frontend-ahmedikram`. Actual bucket is `laad-frontend-676433090516` (account ID based). Using secret avoids confusion. | orchestrator |
| D17 | 2026-06-21 | Trivy action `0.29.3` → `v0.36.0` in `ci.yml` | Tag `0.29.3` deleted during March 2026 supply chain remediation. `v0.36.0` is latest safe version with `v` prefix (post-remediation convention). | orchestrator |
| D18 | 2026-06-21 | CD `workflow_run` references `["CI"]` (not `["LAAD CI"]`) | CI workflow is named `CI`. CD trigger was set to `LAAD CI` which never matched, preventing CD from auto-running after CI success. Fixed to `["CI"]` to match. | orchestrator |
| D19 | 2026-06-21 | Actions upgraded to Node 24-compatible versions: checkout@v5, configure-aws-credentials@v6, setup-buildx-action@v4, cache@v5 | GitHub runners switched to Node 24 as default on June 16, 2026. Older action versions use Node 20 which is deprecated. `amazon-ecr-login@v2` already supports Node 24 via v2.1.x. | orchestrator |
| D20 | 2026-06-21 | IAM trust policy sub claim: `ahmedikram` → `ahmedikram05`; S3 bucket ARN: `ahmedikram` → `676433090516` | GitHub repo owner is `AhmedIkram05` (with `05` suffix). OIDC sub claim uses normalized lowercase `ahmedikram05/laad`, but trust policy had `ahmedikram/laad` — mismatch caused `Not authorized to perform sts:AssumeRoleWithWebIdentity`. S3 bucket uses AWS account ID as unique suffix, not hardcoded `ahmedikram`. | orchestrator |

---

## Quick Reference

### Key Commands (for copying during execution)

```bash
# Terraform apply (gated phases)
cd terraform && terraform init && terraform plan && terraform apply

# Schema init (one-shot, after first deploy)
aws ecs run-task \
  --cluster laad-cluster \
  --task-definition laad-api \
  --overrides '{"containerOverrides":[{"name":"api","command":["python","-c","from backend.src.database.init_db import init_db; init_db(force=False)"]}]}' \
  --launch-type FARGATE \
  --network-configuration '{"awsvpcConfiguration":{"subnets":["'$(terraform output -raw private_subnet_ids)'"],"securityGroups":["'$(terraform output -raw ecs_api_sg_id)'"]}}'

# Force ECS redeploy (all services)
aws ecs update-service --cluster laad-cluster --service laad-api --force-new-deployment
aws ecs update-service --cluster laad-cluster --service laad-consumer --force-new-deployment
aws ecs update-service --cluster laad-cluster --service laad-generator --force-new-deployment

# SageMaker endpoint propagation (Batch 3)
ENDPOINT_NAME=$(terraform output -raw sagemaker_endpoint_name)
aws secretsmanager update-secret --secret-id laad/sagemaker \
  --secret-string "{\"SAGEMAKER_ENDPOINT_NAME\":\"$ENDPOINT_NAME\",\"SAGEMAKER_REGION\":\"eu-west-2\"}"
```

### Timeline Reference

| Phase | Wall-clock | Agents |
|-------|-----------|--------|
| Phase 0 (bootstrap) | ~30 min | Sequential |
| Phase 1 (foundation + code) | ~2-3 hrs | **7 parallel agents** |
| Phase 2 (infra + CI/CD) | ~3-4 hrs | **6 parallel agents** |
| Phase 3 (SageMaker) | ~1-2 hrs | 1 agent |
| Final verification | ~1 hr | You |
| **Total** | **~8-11 hrs** across 2-3 sessions | |
