# Configuration Reference

## Log Generator (`continuous_generator.py`)

| Parameter | Default | Description |
|---|---|---|
| `TICK_SECONDS` | 1 | Interval between emission cycles |
| `ANOMALY_PROB` | 0.02 (2%) | Live anomaly injection probability |
| `BACKFILL_ANOMALY_PROB` | 0.01 (1%) | Backfill anomaly probability |
| `BACKFILL_MINUTES` | 0 | Historical backfill duration (0 = disabled) |
| `ATMS` | 10 | `ATM-GB-0001` through `ATM-GB-0010` |
| `SERVERS` | 3 | `ATM-SERVER-001` through `ATM-SERVER-003` |
| `ALL_ENTITIES` | 13 | Combined list of ATMs + Servers |
| `ATM_LOCATIONS` | 10 | `LOC-001` through `LOC-010` |
| `POD_NAME` | `terminal-handler-pod-0` | Kubernetes pod identifier |
| `OS_VERSION` | `Windows-Server-2019` | Simulated OS version |

## Kafka Broker

| Parameter | Value |
|---|---|
| Image | `confluentinc/cp-kafka:7.5.0` |
| Mode | KRaft (no ZooKeeper) |
| Log retention | 168 hours (7 days) |
| Port | `localhost:9092` (external), `9092` (internal) |

### Topics

| Topic | Partitions | Replication | Message Types |
|---|---|---|---|
| `atm-events` | 3 | 1 | Events (ATM_APP, HARDWARE, TERMINAL_HANDLER, KAFKA) |
| `atm-metrics` | 3 | 1 | Metrics (PROMETHEUS, OS, CLOUD, KAFKA) |

### Producer (`producer.py`)

| Parameter | Value | Rationale |
|---|---|---|
| `acks` | `all` | Zero data loss — all ISR replicas acknowledge |
| `retries` | 5 | Transient broker error resilience |
| `retry_backoff_ms` | 200 | Backoff between retries |
| `compression_type` | `gzip` | ~60% compression ratio |
| `linger_ms` | 10 | Batch messages for throughput |
| `batch_size` | 16384 (16KB) | Default |

### Consumer (`consumer.py`)

| Parameter | Value | Rationale |
|---|---|---|
| `group_id` | `atm-platform-consumer` | Single consumer group |
| `auto_offset_reset` | `latest` | Skip historical on restart |
| `enable_auto_commit` | `false` | Manual commit after batch |
| `max_poll_records` | 500 | Balance throughput vs memory |
| `session_timeout_ms` | 30,000 | 30s dead consumer detection |
| `heartbeat_interval_ms` | 10,000 | Heartbeat every 10s |
| `poll_timeout_ms` | 1,000 | Responsive shutdown |

## Redis

| Variable | Default | Description |
|---|---|---|
| `REDIS_HOST` | `localhost` | Server hostname |
| `REDIS_PORT` | `6379` | Server port |
| `REDIS_DB` | `0` | Database number |
| `REDIS_PASSWORD` | (none) | Auth password |
| `REDIS_CACHE_TTL` | `300` | Default TTL (seconds) |

## ChromaDB Buffer

| Parameter | Value | Description |
|---|---|---|
| Window size | 10 events per ATM | Flushes when buffer reaches 10 |
| Embedding model | `nomic-embed-text` (Ollama container) | 384-dimensional embeddings, served by local `ollama` service |
| Chunker | LangChain `SemanticChunker` | Semantic boundary-based chunking |
| Collection | `atm_logs` | Single collection |
| Vector space | Cosine similarity (HNSW) | Default HNSW index |

## Database Connection Pool

| Parameter | Value |
|---|---|
| Pool type | `ThreadedConnectionPool` |
| minconn | 5 |
| maxconn | 50 |
| Retry attempts | 3 |
| Backoff | Exponential (100ms → 200ms) |
| Cursor type | `RealDictCursor` |

## ML Inference

| Parameter | Default | Description |
|---|---|---|
| `ML_WINDOW_SECONDS` | 600 | Data window for inference queries (was 60s, bumped to 600s to capture longer anomaly cascades) |
| `ML_UNKNOWN_THRESHOLD` | -0.75 | IF score threshold for UNKNOWN classification (overridden by trained artifact `if_unknown_threshold.json`) |
| `ML_WARMUP_CYCLES` | 2 | Number of initial detection cycles to skip UNKNOWN savings (prevents cold-start flood; typed A1-A7 still save) |

## ML Training

| Parameter | Value |
|---|---|
| Window size | 60 seconds |
| Step size | 30 seconds |
| Query window (LIVE) | 360 minutes (6 hours) |
| Min rows per window | 5 |
| CV folds | up to 5 (StratifiedKFold) |
| Class balancing | `sample_weight = normal_count / class_count` |

### XGBoost

| Hyperparameter | Value |
|---|---|
| `n_estimators` | 100 |
| `max_depth` | 6 |
| `learning_rate` | 0.1 |
| `subsample` | 0.8 |
| `colsample_bytree` | 0.8 |
| `eval_metric` | `mlogloss` |

### Isolation Forest

| Hyperparameter | Value |
|---|---|
| `n_estimators` | 200 |
| `contamination` | `'auto'` |
| `max_features` | `1.0` |
| `max_samples` | `0.7` |
| `bootstrap` | `True` |

## RAG

| Parameter | Default | Description |
|---|---|---|
| `LLM_API_KEY` | (required) | W&B Serverless Inference API key (or `WANDB_API_KEY`) |
| `LLM_BASE_URL` | https://api.inference.wandb.ai/v1 | W&B Serverless Inference endpoint |
| `LLM_MODEL` | google/gemma-4-31B-it | Model for all RAG LLM calls |
| `RAG_JUDGE_MODEL` | Qwen/Qwen3-30B-A3B-Instruct-2507 | Eval-only judge model (RAGAS scoring) |
| `RAG_RATE_LIMIT` | 20 | Client-side LLM rate limit per minute (0 = off) |
| `RAG_TOP_K` | 10 | Retrieved chunks |
| `RAG_CHUNK_TRUNCATE` | 800 | Chars per chunk |
| `RAG_ERROR_ONLY` | true | Filter ERROR/FATAL |
| `RAG_SAMPLES` | 3 | Self-consistency samples |
| `CONF_HIGH` / `CONF_MEDIUM` | 0.8 / 0.5 | Confidence thresholds |
| `RAG_REFLEXION` | true | Enable self-critique |
| `RAG_CITATION_GROUNDING` | true | Citation verification |
| `RAG_SELF_CONSISTENCY` | true | Scoring enable |
| `RAG_CROSS_ENCODER` | true | Reranking enable |
| `RAG_CROSS_ENCODER_MODEL` | cross-encoder/ms-marco-MiniLM-L-2-v2 | Model name |

## Docker Services

| Service | External Port | Internal Port |
|---|---|---|
| PostgreSQL | 5434 | 5432 |
| Test PostgreSQL | 5433 | 5432 |
| Kafka | 9092 | 9092 |
| ChromaDB | 8001 | 8000 |
| Ollama | 11435 | 11434 |
| MCP Server | 8002 | 8001 |
| Backend API | 8000 | 8000 |
| MLflow | 5001 | 5000 |

## Docker Volumes

| Volume | Service | Purpose |
|---|---|---|
| `postgres_data` | postgres | Persistent database data |
| `kafka_data` | kafka | Kafka log segments |
| `chroma_data` | chromadb | ChromaDB collection data |
| `ollama_data` | ollama | Ollama model storage (nomic-embed-text, ~274MB) |
| `mlflow_artifacts` | mlflow | MLflow model artifacts |
| `postgres_test_data` | postgres_test | Test database data |
