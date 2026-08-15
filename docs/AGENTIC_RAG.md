# Agentic Hybrid RAG

Agentic hybrid RAG for the LAAD observability backend: a LangGraph agent over
12 MCP tools that routes retrieval between vector search, structured
metric/anomaly queries, and the anomaly-knowledge store — with self-critique
(Reflexion), self-consistency scoring, and citation grounding.

Spec: [`docs/agentic-rag-retrofit-plan.md`](agentic-rag-retrofit-plan.md).

## Goal

Answer natural-language questions about logs, metrics, and anomalies with
verifiable, cited answers — choosing the right tool per question instead of a
single fixed retriever. Three systems are evaluated against each other:

| System | Retrieval | Notes |
|---|---|---|
| `baseline` | Fixed: chroma semantic + SQL full-text, fused | No agent, no LLM rerank |
| `hybrid` | Agent chooses tools (search_knowledge + structured) | Deterministic routing rules |
| `agentic` | Agent routes + Reflexion + self-consistency + citation grounding | Highest quality, ~3× cost |

## Architecture

```
user question
   │
   ▼
FastAPI POST /api/rag/agent  ──►  LangGraph StateGraph (backend/src/rag/agent.py)
   │                                  │
   │                                  ├─► MCP tools (backend/src/mcp/*.py)
   │                                  │      search_knowledge · query_anomalies
   │                                  │      get_anomaly · get_machine_history
   │                                  │      get_atm_metrics · get_statistics
   │                                  │      search_events · get_error_context
   │                                  │      get_atm_info · compare_atms
   │                                  │      get_anomaly_class_info
   │                                  │      get_rag_collection_stats
   │                                  ├─► RAG pipeline: retriever → generator →
   │                                  │      uncertainty → citations
   │                                  └─► trace (rag_agent_traces table)
   ▼
AgentQueryResponse { answer, sources, confidence, citations, trace_id, ... }
```

Components:

- **MCP server** (`backend/src/mcp/server.py`) — exposes the twelve tools over
  the Model Context Protocol; `adapter.get_langchain_tools()` converts them to
  LangChain tools for the graph (standalone MCP run: `python -m backend.src.mcp.server`).
- **Graph** (`backend/src/rag/agent.py`) — `run_agent_query` entry point; nodes
  for tool selection, execution, Reflexion, self-consistency, and citation
  grounding; `AgentMode.HYBRID` vs `AgentMode.AGENTIC`.
- **Retriever / generator / uncertainty** (`backend/src/rag/`) — chroma
  semantic + SQL full-text fusion, LLM generation, confidence estimation from
  generation variance.
- **Persistence** — every run writes a trace row to `rag_agent_traces`; the
  `/api/rag/agent` endpoint returns the trace id.

## Running the MCP server standalone

The MCP server is a real, network-reachable service (not a library call) —
any MCP client can attach to it directly:

```bash
docker compose up -d mcp-server          # starts SSE transport on port 8001 (container)
```

- The compose service publishes **host port 8002** → container 8001 (host 8001
  is taken by chromadb's `8001:8000` mapping), so external clients connect to
  `http://localhost:8002/sse`.
- Internal consumers (`backend`, `pytest` services) use
  `MCP_SERVER_URL=http://mcp-server:8001/sse` over the compose network —
  unchanged.
- To inspect the tools interactively:

  ```bash
  npx @modelcontextprotocol/inspector http://localhost:8002/sse
  # or point any MCP client (Claude Desktop, Codex, ...) at the same URL
  ```

- Healthcheck: `python -c 'import socket; socket.create_connection(("localhost", 8001), 2)'`
  (container-side).

`adapter.get_langchain_tools()` uses the SSE transport whenever
`MCP_SERVER_URL` is set; without it (unit tests, `--smoke`), it falls back to
an in-process session against the same `FastMCP` instance.

## Evaluation

Harness: `backend/tests/eval/` (RAGAS 0.4.x, golden set, seeds, report).

- **Golden set** — 50 queries, 5 categories × 10 (semantic, structured,
  hybrid, adversarial, no-data), 25 reviewed with human verdicts;
  `backend/tests/eval/golden_set.json`.
- **Seed data** — `backend/tests/eval/seed.py` (idempotent, deterministic):
  6 anomalies, 11 metrics, 5 events, 6 chroma scenarios.
- **Metrics** — `context_recall`, `faithfulness`,
  `llm_context_precision_with_reference`, `answer_relevancy`.
- **Agent metrics** (report only) — tool_selection_accuracy, retrieval
  efficiency, unnecessary-tool-call rate, agent success rate, retry rate,
  mean end-to-end latency, estimated cost/query.
- **Guardrail suite** — G1–G17 (`backend/tests/test_agent_guardrails.py`):
  rate limit, sanitization, cache key, truncation backstop, no-answer paths,
  PII, ATM scoping, mode routing, etc.

Run the eval (`make eval-ragas`, FLAGS passthrough):

```bash
# quick iteration (1 LLM call/query, D13 inert, cross-encoder off)
make eval-ragas FLAGS="--fast --limit 10"

# production config, first 20 golden queries
make eval-ragas FLAGS="--limit 20"

# full production config + refresh the committed baseline
make eval-ragas FLAGS="--refresh-baseline --baseline docs/eval/baseline.json"

# CI gate (regression vs committed baseline)
make eval-ragas FLAGS="--baseline docs/eval/baseline.json"
```

Render the report (global/per-category/agent metrics, adversarial pass/fail
matrix, cost-vs-quality):

```bash
python -m backend.tests.eval.report            # latest run
python -m backend.tests.eval.report --baseline # committed baseline
```

Smoke test (3 mini queries × 3 systems + ragas round-trip):
`python -m pytest backend/tests/test_agentic_rag_smoke.py -m rag`.

**CI gate** (`.github/workflows/eval-gate.yml`) runs the eval on PRs and
`main`, compares against `docs/eval/baseline.json`, fails on regression
(faithfulness < 0.5, context_recall < 0.3, or any metric drop > 0.05), and
uploads `eval_results/` as an artifact. Neutral (green) when no
`WANDB_API_KEY` secret is configured.

## Results

See `backend/tests/eval/results.json` (latest run), `docs/eval/baseline.json`
(committed baseline), and `python -m backend.tests.eval.report` for the
human-readable tables. Expected trend: agentic ≥ hybrid ≥ baseline on
faithfulness and context precision, at ~3× the cost per query.

## Limitations

- Cross-encoder reranking is disabled when `sentence-transformers` is missing
  (e.g. minimal test images) — eval scores then reflect no-rerank retrieval.
- The eval judge model (`RAG_JUDGE_MODEL`) and generation model (`LLM_MODEL`)
  are W&B serverless only; the gate is neutral without a `WANDB_API_KEY`.
- Never run pytest suites (`backend/tests/conftest.py` truncates the shared
  `atm_platform_test` DB) while an eval container is executing.
  