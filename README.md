# ATM Log Aggregation, Anomaly Detection & Diagnostics Platform (LAAD)

> An ATM log platform: Kafka ingestion → 3-layer anomaly detection → FastAPI → React dashboard, plus an agentic RAG diagnostic assistant - deployed on AWS ECS Fargate with SageMaker inference.

<p align="center">
<a href="https://www.python.org/"><img src="https://img.shields.io/badge/Python-3776AB?style=for-the-badge&labelColor=000000&logo=python"></a>
<a href="https://docs.python.org/3/library/asyncio.html"><img src="https://img.shields.io/badge/asyncio-3776AB?style=for-the-badge&labelColor=000000&logo=python"></a>
<a href="https://fastapi.tiangolo.com/"><img src="https://img.shields.io/badge/FastAPI-009688?style=for-the-badge&labelColor=000000&logo=fastapi"></a>
<a href="https://www.langchain.com/"><img src="https://img.shields.io/badge/LangChain-1C3C3C?style=for-the-badge&labelColor=000000&logo=langchain"></a>
<a href="https://www.langchain.com/langgraph"><img src="https://img.shields.io/badge/LangGraph-7C3AED?style=for-the-badge&labelColor=000000"></a>
<a href="https://modelcontextprotocol.io/"><img src="https://img.shields.io/badge/MCP-7C3AED?style=for-the-badge&labelColor=000000&logo=modelcontextprotocol"></a>
<a href="https://www.postgresql.org/"><img src="https://img.shields.io/badge/PostgreSQL-003B57?style=for-the-badge&labelColor=000000&logo=postgresql"></a>
<a href="https://kafka.apache.org/"><img src="https://img.shields.io/badge/Kafka-231F20?style=for-the-badge&labelColor=000000&logo=apachekafka"></a>
<a href="https://redis.io/"><img src="https://img.shields.io/badge/Redis-DC382D?style=for-the-badge&labelColor=000000&logo=redis"></a>
<a href="https://www.chromadb.com/"><img src="https://img.shields.io/badge/ChromaDB-000000?style=for-the-badge&labelColor=5F3DC8"></a>
<a href="https://docs.ragas.io/"><img src="https://img.shields.io/badge/RAGAS-0078D4?style=for-the-badge&labelColor=000000"></a>
<a href="https://nginx.org/"><img src="https://img.shields.io/badge/Nginx-009639?style=for-the-badge&labelColor=000000&logo=nginx"></a>
<a href="https://xgboost.ai/"><img src="https://img.shields.io/badge/XGBoost-0052CC?style=for-the-badge&labelColor=000000"></a>
<a href="https://scikit-learn.org/"><img src="https://img.shields.io/badge/scikit--learn-F7931E?style=for-the-badge&labelColor=000000&logo=scikitlearn"></a>
<a href="https://pandas.pydata.org/"><img src="https://img.shields.io/badge/Pandas-150458?style=for-the-badge&labelColor=000000&logo=pandas"></a>
<a href="https://ollama.ai/"><img src="https://img.shields.io/badge/Ollama-000000?style=for-the-badge&labelColor=000000&logo=ollama"></a>
<a href="https://aws.amazon.com/sagemaker/"><img src="https://img.shields.io/badge/SageMaker-232F3E?style=for-the-badge&labelColor=000000&logo=amazonwebservices"></a>
<a href="https://mlflow.org/"><img src="https://img.shields.io/badge/MLflow-0194E2?style=for-the-badge&labelColor=000000&logo=mlflow"></a>
<a href="https://opentelemetry.io/"><img src="https://img.shields.io/badge/OpenTelemetry-425CC7?style=for-the-badge&labelColor=000000&logo=opentelemetry"></a>
<a href="https://react.dev/"><img src="https://img.shields.io/badge/React-61DAFB?style=for-the-badge&labelColor=000000&logo=react"></a>
<a href="https://vite.dev/"><img src="https://img.shields.io/badge/Vite-646CFF?style=for-the-badge&labelColor=000000&logo=vite"></a>
<a href="https://tailwindcss.com/"><img src="https://img.shields.io/badge/Tailwind_CSS-06B6D4?style=for-the-badge&labelColor=000000&logo=tailwindcss"></a>
<a href="https://www.chartjs.org/"><img src="https://img.shields.io/badge/Chart.js-FF6384?style=for-the-badge&labelColor=000000&logo=chartdotjs"></a>
<a href="https://www.docker.com/"><img src="https://img.shields.io/badge/Docker-2496ED?style=for-the-badge&labelColor=000000&logo=docker"></a>
<a href="https://www.terraform.io/"><img src="https://img.shields.io/badge/Terraform-7B42BC?style=for-the-badge&labelColor=000000&logo=terraform"></a>
<a href="https://github.com/features/actions"><img src="https://img.shields.io/badge/GitHub_Actions-2088FF?style=for-the-badge&labelColor=000000&logo=githubactions"></a>
<a href="https://aws.amazon.com/"><img src="https://img.shields.io/badge/AWS-232F3E?style=for-the-badge&labelColor=000000&logo=amazonwebservices"></a>
</p>

<p align="center">
<a href="https://github.com/AhmedIkram05/laad/actions/workflows/ci.yml"><img src="https://github.com/AhmedIkram05/laad/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
<a href="https://github.com/AhmedIkram05/laad/actions/workflows/cd.yml"><img src="https://github.com/AhmedIkram05/laad/actions/workflows/cd.yml/badge.svg" alt="CD"></a>
<a href="https://github.com/AhmedIkram05/laad/actions/workflows/terraform.yml"><img src="https://github.com/AhmedIkram05/laad/actions/workflows/terraform.yml/badge.svg" alt="Terraform"></a>
<a href="https://github.com/AhmedIkram05/laad/actions/workflows/eval-gate.yml"><img src="https://github.com/AhmedIkram05/laad/actions/workflows/eval-gate.yml/badge.svg" alt="RAG Eval"></a>
<a href="https://codecov.io/gh/AhmedIkram05/laad"><img src="https://codecov.io/gh/AhmedIkram05/laad/branch/main/graph/badge.svg" alt="Codecov"></a>
</p>

<video src="https://github.com/user-attachments/assets/e3a59f59-8d6f-419b-87da-e520be77ccf6" title="Detected anomalies across ATM and server systems, prioritised by criticality score" controls></video>

## How It Fits Together

```mermaid
flowchart LR
  subgraph SRC["Sources"]
    S[7 log sources]
  end
  subgraph STREAM["Streaming + state"]
    K["Kafka (KRaft)"]
    R[(Redis<br/>dedup + DLQ)]
  end
  subgraph DETECT["Detection + storage"]
    D[3-layer detection]
    M[SageMaker cross-check]
    P[(PostgreSQL + ChromaDB)]
  end
  subgraph SERVE["Serving"]
    A[FastAPI · 30 endpoints]
    CF[CloudFront]
    F[React dashboard]
    G[Agentic RAG assistant]
  end
  S --> K
  K --> D
  K --> P
  K --> R
  M --> D
  D --> A
  P --> A
  A --> CF --> F
  A --> G
```

7 log sources → Kafka (gzip, acks=all) → deduplicated, parsed, dual-written to PostgreSQL + ChromaDB. A 3-layer detector runs every 30s with live SageMaker cross-check; FastAPI serves the dashboard and the RAG assistant. Full 30-node topology: [System Architecture](docs/README-full.md#system-architecture).

## Every Piece, in One Line

| Component | What it does |
| --- | --- |
| **7 log sources** | ATM application logs, hardware-sensor metrics, terminal-handler logs, and Kafka/Prometheus/Windows/GCP metrics stream from a single generator - pure Kafka producers (gzip, `acks=all`), no direct DB writes |
| **Kafka (KRaft)** | 2 topics × 3 partitions (`atm-events`, `atm-metrics`), 7-day retention; the consumer deduplicates (Redis SET + LRU), parses via 7 source-specific parsers, dual-writes to PostgreSQL + ChromaDB, and routes failures to a Redis Stream DLQ |
| **Detection engine** | 3 layers - XGBoost + Isolation Forest ensemble, rolling 20-window Z-score, 7 deterministic heuristics - running every 30s, cross-checked against the live SageMaker endpoint |
| **PostgreSQL 16** | Unified events/metrics schema: 10 tables, 3 views, 15 indexes, JSONB; adding a source = new parser, zero schema change |
| **ChromaDB** | `atm_logs` collection with 768-dim `nomic-embed-text` embeddings generated locally by Ollama - the RAG assistant's vector memory |
| **FastAPI** | 30 endpoints across 6 routers (auth, anomalies, entities, analysis, admin, RAG) - the one API every consumer hits |
| **React dashboard** | 9 pages, KPI cards polling every 5s, Chart.js analytics, served via CloudFront in production |
| **Agentic RAG** | LangGraph assistant with 12 MCP tools and 4-stage reasoning over the same unified data |
| **SageMaker** | `laad-xgb-champion` (XGBoost 1.7-1, `ml.t2.medium`): 8-class softmax in ~100ms, live-validating detector output |
| **OpenTelemetry tracing** | Distributed traces across the four Python services — RAG query and event-pipeline golden paths browsable in Jaeger (dev): [docs/observability.md](docs/observability.md) · [docs/demos](docs/demos/) |

## Why It's Interesting

| Highlight | Why It Matters |
| --- | --- |
| **Effectively-once Kafka, without Kafka transactions** | Manual offset commits + a 10K-LRU idempotency filter keyed by `message_id` give at-least-once delivery with effectively-once semantics inside the window. [Deep dive](docs/README-full.md#kafka-message-bus) |
| **A confidence system that knows when it's wrong** | Four signals fused as an uncertainty-weighted average with static calibrated weights; missing signals are renormalised away, so the assistant degrades gracefully instead of faking certainty. [Deep dive](docs/README-full.md#agentic-hybrid-rag-diagnostic-assistant-1) |
| **Two models that answer two different questions** | XGBoost classifies the 8 known anomaly classes; the Isolation Forest sidecar separately flags "something is off, but it's not one of the known shapes" - a distinction most anomaly projects skip. [Deep dive](docs/README-full.md#3-layer-anomaly-detection-engine-1) |
| **SageMaker as a cross-check, not a crutch** | Local inference in ~30ms keeps detection independent of the cloud; SageMaker (~100ms) adds an external second opinion per prediction without ever becoming a hard dependency. |

## Key Metrics

| Metric | Value |
| --- | --- |
| Anomaly detection | XGBoost 8-class CV **99.0%** (temporal-holdout macro-F1 **0.94**, 0.93 on a held-out second generator config, 7,192 windows) · Isolation Forest **94.0%** precision |
| RAG quality (RAGAS, agentic) | faithfulness **0.940** · precision **0.874** · relevancy **0.801** |
| Throughput | **~100 msgs/sec** sustained on one consumer · **2.5M+** events processed |
| API surface | **30 endpoints** across 6 routers |
| Tests gating every PR | **1,846** (1,311 pytest expanded · 495 vitest · 10 Playwright · 30 Terraform) + 26 security checks |
| Infrastructure | **10 Terraform modules / 114 resources (+6 bootstrap)** on AWS: ECS Fargate, RDS, SageMaker, CloudFront, VPC |
| Inference latency | local ~30ms · SageMaker cross-check ~100ms |

> **Metrics provenance:** throughput (~100 msgs/sec) and 2.5M+ events are live-pipeline figures from the commissioning deployment - the committed demo seed is 56.9K events - and sub-100ms query latency is a running-instance measurement, not a committed benchmark. RAG eval artifacts: [backend/tests/eval/golden_set.json](backend/tests/eval/golden_set.json) · [docs/eval/baseline.json](docs/eval/baseline.json).

## AI - detection & diagnostics

- **3-layer detector** - XGBoost 8-class classifier at **99.0% CV accuracy (temporal-holdout macro-F1 0.94; 0.93 macro-F1 on a held-out second generator configuration — different seed, shifted class mix)** plus an Isolation Forest sidecar (**94.0% precision**, 0.78 AUC-ROC) for out-of-class novelty, Z-score drift detection, and always-on heuristics. SageMaker (`ml.t2.medium`) validates predictions live. [Deep dive](docs/README-full.md#3-layer-anomaly-detection-engine-1)
- **Agentic Hybrid RAG** - True-hybrid retrieval (dense `nomic-embed-text` + BM25 sparse → RRF k=60 → temporal boost → cross-encoder `ms-marco-MiniLM-L-2-v2`), LangGraph with 12 MCP tools, 4-stage reasoning, and 4-signal confidence fusion via uncertainty-weighted averaging (static calibrated weights). RAGAS-evaluated (agentic): **faithfulness 0.940, precision 0.874, relevancy 0.801**. [Deep dive](docs/README-full.md#agentic-hybrid-rag-diagnostic-assistant-1) · [Evaluation data](docs/eval/) · [Per-system numbers](docs/eval/baseline.json)
  - *Hybrid retrieval* = dense + BM25 fused via RRF inside `search_knowledge` (both modes). *Hybrid mode* = deterministic planner (`search_knowledge` + ≤1 structured tool, 0 planning LLM calls, never retries). *Agentic mode* = free-form tool loop with grounding-gated retry (<0.6).

  <video src="https://github.com/user-attachments/assets/aad8a189-0d2e-4de0-9a8f-ff04e8dc6ba3" title="Diagnostic assistant chat interface with example queries" controls></video>

- **MLOps** - MLflow on AWS (RDS + S3), 7 artifacts per run, champion aliases, auto-retrain when artifacts go missing or corrupt. [Deep dive](docs/README-full.md#ml-training--mlops)

  <video src="https://github.com/user-attachments/assets/1807441a-6208-43cf-984d-8a8452212df7" title="MLflow experiment tracking for atm-anomaly-detection" controls></video>

## Data engineering - the spine

- **Kafka pipeline** - **~100 msgs/sec sustained** on a single consumer, **2.5M+ events** through the live pipeline: KRaft broker, 2 topics × 3 partitions, 7 source-specific parsers, Redis-SET deduplication, **manual offset commits** (at-least-once, effectively-once within the LRU window), failures routed to a Redis Stream DLQ with retry + backoff. [Deep dive](docs/README-full.md#kafka-message-bus)

  <video src="https://github.com/user-attachments/assets/faf59298-5710-4a79-84d8-fbdafdcf789d" title="Kafka consumer streaming events into ChromaDB (200 OK upserts)" controls></video>
- **PostgreSQL 16** - unified events/metrics schema with JSONB, 15 indexes, and a `v_unified_analysis` view for time-window semantics. Adding a log source = new parser, zero schema change. [Deep dive](docs/README-full.md#database-design)
- **Redis** - 8 patterns (rate limiting, dedup, locking, Pub/Sub, caching, DLQ, analytics) off one connection pool, each degrading gracefully. [Deep dive](docs/README-full.md#redis-infrastructure-8-patterns)

## IaC - the estate

- **Terraform** - 10 modules, 114 resources (+6 bootstrap): VPC across 2 AZs, ECS Fargate, RDS, SageMaker, CloudFront, Secrets Manager, least-privilege IAM. State locked in DynamoDB + versioned in S3; CI auth via OIDC - no long-lived credentials. [Deep dive](docs/README-full.md#aws-deployment--infrastructure)

  <video src="https://github.com/user-attachments/assets/8c955dba-585d-4569-b336-6d21160df0b1" title="AWS estate tour: VPC, ECS Fargate, ALB, Kafka EC2, CloudFront, IAM, Secrets Manager, SageMaker, S3 versioning - cycles every 3s" controls></video>

## Observability - Distributed Traces

Every RAG query and every synthetic event can be followed end-to-end across services with [OpenTelemetry](https://opentelemetry.io): FastAPI → MCP tools → LLM → Redis/DB on the query path, generator → Kafka → consumer → detection on the pipeline path — W3C trace context propagates through Kafka message headers, so **one trace spans four services**.

**Trace walkthrough** - RAG query path → confidence gate → event pipeline:

<video src="https://github.com/user-attachments/assets/58ac557f-bc5f-460f-8393-e6e81dfaab79" title="Jaeger trace walkthrough - RAG golden path, gate decision close-up, event pipeline" controls></video>

The gate close-up is the one worth pausing on - it's the same confidence machinery that decides answer-vs-escalate, now visible per query. Full contract and ops defaults in [docs/observability.md](docs/observability.md).

**What's actually running:**

| Layer | Deployment detail |
| --- | --- |
| Network | VPC `10.0.0.0/16` in eu-west-2, 2 AZs: public subnets host only the ALB + NAT; all application traffic in private subnets, outbound via NAT |
| Compute | ECS Fargate: API service (2 tasks, 2 vCPU / 4GB, Uvicorn ×4) + Consumer service (2 tasks: Kafka ingest + detection engine), rolling updates |
| Broker node | One EC2 in a private subnet hosts Kafka (KRaft), Redis 7, ChromaDB, and Ollama - no network egress, models stay local |
| Databases | App PostgreSQL 16 beside Kafka on the EC2 node (deliberate cost call); MLflow tracking on managed RDS 18.4 with automated backups |
| Storage | 3 S3 buckets - React assets (served via CloudFront), MLflow artifacts (model binaries), Terraform state (versioned + DynamoDB-locked) |
| ML inference | SageMaker endpoint deployed from the MLflow `champion` alias - model saved as JSON for the XGBoost 1.7-1 container |
| Secrets & IAM | Secrets Manager injected straight into ECS task definitions (no `.env` files); least-privilege role per service; GitHub → AWS via OIDC, zero long-lived keys |

- **Quality gates** - **1,846 tests** (base 1,802) gating every PR (1,311 pytest expanded [1,267 base + 44 param] across 10 tiers · 495 vitest · 10 Playwright E2E · 30 Terraform runs [104 asserts]), plus 26 security checks. [Deep dive](docs/README-full.md#testing--quality)

  <video src="https://github.com/user-attachments/assets/4664af25-f549-45d1-9333-0391a051f27d" title="Quality gates tour: CI matrix, CD, Terraform plan/apply, pytest 1288 passed, vitest 495/55 suites, E2E 10, stress 8" controls></video>
- **Frontend** - React 19 + Vite + Tailwind v4: 9 pages, KPI cards polling every 5s, Chart.js analytics, shipped as a ~25MB nginx image. [Deep dive](docs/README-full.md#frontend-architecture)

  <video src="https://github.com/user-attachments/assets/19d7ede8-d000-4e01-bfec-714f206448a7" title="Analytics dashboard: 56.9K events, 41 anomalies, 8 types detected" controls></video>

## Trade-offs That Mattered

| Decision | Alternative | Why it won |
| --- | --- | --- |
| **3 detection layers, not ML-only** | ML-only, heuristic-only | Independent failure modes: ML catches the 8 known classes, Z-score catches drift, heuristics are the always-on net |
| **XGBoost + Isolation Forest ensemble** | Single XGBoost, LSTM | XGBoost scores the 8 known classes; the unsupervised sidecar catches novelty outside them - "known anomaly" vs "something's wrong" |
| **Uncertainty-weighted 4-signal confidence fusion** | LLM verbalised or retrieval-only confidence | Any single signal misleads; weighted fusion degrades gracefully and resists hallucination |
| **Kafka (KRaft) + manual offset commits** | Redis Pub/Sub, auto-commit | Disk persistence and offset replay; auto-commit risks message loss on crash |
| **Self-hosted ChromaDB + local embeddings** | Pinecone, Weaviate | No per-vector API costs, log data never leaves the network, 768-dim embeddings via local Ollama |
| **Unified PostgreSQL (no TimescaleDB)** | TimescaleDB for metrics | 100+ msg/s under 100ms queries without extension lock-in; `PARTITION BY RANGE` is one DDL away if throughput grows 10× |
| **Entire AWS estate in Terraform** | Console/manual provisioning | Rebuildable in one run, state locked + versioned, 30 runs (104 asserts) in CI |

All 11 recorded decisions with the full reasoning: [Design Decisions](docs/README-full.md#design-decisions)

## Quick Start

```bash
git clone https://github.com/AhmedIkram05/laad.git && cd laad
cp .env.example .env
make all   # everything in Docker: frontend, API, Kafka, detection, RAG
```

Frontend on `:5173` · API on `:8000/docs` · MLflow on `:5001` · Postgres on `:5434`. Default login `admin`/`admin`. [Configuration reference](docs/configuration.md)

> **Running tests locally:** a bare `pytest --collect-only` can report module-collection errors unless the optional extras (chromadb, kafka, ML dependencies) are installed - the full 1,311-backend-test expanded count (1,267 base + 44 param) materializes when all extras are present ([ci.yml](.github/workflows/ci.yml)).

## Documentation

- **Everything, in full** - the complete 1,424-line document, preserved verbatim: [docs/README-full.md](docs/README-full.md)
- [API reference](docs/api-reference.md) · [Configuration](docs/configuration.md) · [Anomaly detection guide](docs/anomaly_detection_guide.md) · [RAG evaluation](docs/eval/) · [Demos & media](docs/README-full.md#demos) · [Data dictionary](docs/Data%20Dictionary/) · [Academic project report](docs/Project-Report.pdf)

## About This Project

Started as the CS32002 Industrial Team Project at the University of Dundee, built for **NCR Atleos** (team foundation: rule-based detection and a single-script generator). The Kafka pipeline, 3-layer ML detection, MLOps, the agentic RAG assistant, the 1,846-test suite, the 30-endpoint API, and the entire AWS estate above were designed, built, and deployed by **Ahmed Ikram** as an independent post-submission extension. [Team breakdown](docs/README-full.md#team)

## Related Projects

- [DevSync](https://github.com/AhmedIkram05/DevSync) - full-stack project tracker with real-time collaboration and GitHub OAuth integration
- [W3C-ETL-Pipeline](https://github.com/AhmedIkram05/W3C-ETL-Pipeline) - serverless Azure ETL: W3C web logs through Databricks DLT → dbt → Power BI
- [StockLens](https://github.com/AhmedIkram05/StockLens) - FinTech mobile app: OCR receipt scanning, portfolio analytics, LSTM forecasting, self-built MCP server
