"""RAGAS evaluation runner for the agentic-RAG retrofit.

Compares baseline / hybrid / agentic systems on the golden set (50 queries)
using four ragas metrics: LLMContextRecall, Faithfulness,
LLMContextPrecisionWithReference, AnswerRelevancy.

Usage (inside the pytest container, after seeding):
    python -m backend.tests.eval.run_ragas [--systems baseline hybrid agentic]
                                           [--refresh-baseline]
                                           [--out results.json]
"""
from __future__ import annotations

import argparse
import asyncio
import json
import math
import hashlib
import os
import sys
import time
import types
from pathlib import Path

# --fast / --smoke: run with the §7.5 smoke config (1 LLM call per generation
# instead of ~7) so a full run fits in ~15 min (--fast) or a wiring check in
# seconds (--smoke). Production defaults (RAG_SAMPLES=3, reflexion,
# self-consistency) stay for other runs; D13 is inert under these pins, and
# the cross-encoder (CPU, ~1-2s/query) is skipped. Must be set BEFORE config
# is imported (module-level config reads env).
_FAST_ENV = {
    "RAG_SAMPLES": "1",
    "RAG_REFLEXION": "false",
    "RAG_SELF_CONSISTENCY": "false",
    "RAG_CITATION_GROUNDING": "false",
    "RAG_CROSS_ENCODER": "false",
}
if "--fast" in sys.argv or "--smoke" in sys.argv:
    os.environ.update(_FAST_ENV)

# --smoke wiring check: a hard-coded mini-set (no golden set dependency) that
# exercises all three systems and asserts a score dict (plan §7.5).
_SMOKE_QUERIES = [
    {"id": "smoke-semantic", "query": "What is the status of ATM-GB-0001?",
     "reference_answer": "ATM-GB-0001 is operational.",
     "expected_tools": ["search_knowledge"], "atm_id": "ATM-GB-0001",
     "query_type": "diagnostic", "category": "semantic"},
    {"id": "smoke-structured", "query": "Show the top memory consumers in the last hour.",
     "reference_answer": "Top consumers listed.",
     "expected_tools": ["query_anomalies"], "atm_id": None,
     "query_type": "stats", "category": "structured"},
    {"id": "smoke-hybrid", "query": "Are there anomalies around ATM-GB-0002?",
     "reference_answer": "Anomalies found.",
     "expected_tools": ["search_knowledge", "query_anomalies"],
     "atm_id": "ATM-GB-0002", "query_type": "diagnostic", "category": "hybrid"},
]

# --- ragas import shim ---------------------------------------------------
# ragas 0.4.x imports ChatVertexAI from langchain_community.chat_models.vertexai
# at module load; langchain-community 0.4 removed it. It is only used in an
# isinstance() allow-list, never instantiated, so a stub suffices.
_stub = types.ModuleType("langchain_community.chat_models.vertexai")
_stub.ChatVertexAI = type("ChatVertexAI", (), {})
sys.modules.setdefault("langchain_community.chat_models.vertexai", _stub)
# --------------------------------------------------------------------------

from ragas import evaluate  # noqa: E402  (after the ChatVertexAI shim above)
from ragas.dataset_schema import EvaluationDataset  # noqa: E402
from ragas.embeddings.base import LangchainEmbeddingsWrapper  # noqa: E402
from ragas.llms.base import llm_factory  # noqa: E402
from ragas.metrics import (  # noqa: E402
    LLMContextPrecisionWithReference,
    LLMContextRecall,
    AnswerRelevancy,
    Faithfulness,
)
from langchain_ollama import OllamaEmbeddings  # noqa: E402

from backend.src.rag.config import config  # noqa: E402
from openai import OpenAI  # noqa: E402

# ragas 0.4.x llm_factory requires a client instance (text-only mode removed).
_judge_client = OpenAI(api_key=config.llm_api_key, base_url=config.llm_base_url)
from backend.src.rag.agent_types import AgentMode  # noqa: E402
from backend.tests.eval.systems import (  # noqa: E402
    GOLDEN_SET_PATH,
    SYSTEMS,
    SystemResult,
    _ensure_patched,
    run_agent,
    run_baseline,
    seed,
)

EVAL_DIR = Path(__file__).parent
BASELINE_PATH = Path(__file__).parents[2] / "docs" / "eval" / "baseline.json"
CACHE_PATH = EVAL_DIR / "cached_results.json"
# Run config that changes query results — the cache must never mix configs
# (e.g. --fast single-sample results vs production 3-sample + reflexion).
_CACHE_SIGNATURE_KEYS = (
    "RAG_SAMPLES",
    "RAG_REFLEXION",
    "RAG_SELF_CONSISTENCY",
    "RAG_CITATION_GROUNDING",
    "RAG_CROSS_ENCODER",
    "RAG_JUDGE_MODEL",
    "RAG_TOP_K",
    "RAG_HYBRID_TOP_K",
    "RAG_EVAL_LIMIT",
)


def _cache_signature() -> str:
    env = {k: os.getenv(k) for k in _CACHE_SIGNATURE_KEYS}
    return hashlib.sha256(json.dumps(env, sort_keys=True).encode()).hexdigest()[:12]
METRICS = [
    ("context_recall", LLMContextRecall()),
    ("faithfulness", Faithfulness()),
    ("llm_context_precision_with_reference", LLMContextPrecisionWithReference()),
    ("answer_relevancy", AnswerRelevancy()),
]
METRIC_NAMES = [name for name, _ in METRICS]

# Gate: absolute floors (any system) and relative drop vs baseline.
FLOORS = {"faithfulness": 0.5, "context_recall": 0.3}
MAX_DROP = 0.05


def _result_to_dict(r):
    return {
        "system": r.system,
        "query_id": r.query_id,
        "query": r.query,
        "reference_answer": r.reference_answer,
        "answer": r.answer,
        "retrieved_contexts": r.retrieved_contexts,
        "agent_trace": r.agent_trace,
        "error": r.error,
    }


def _result_from_dict(d):
    return SystemResult(
        system=d["system"],
        query_id=d["query_id"],
        query=d["query"],
        reference_answer=d["reference_answer"],
        answer=d["answer"],
        retrieved_contexts=d.get("retrieved_contexts", []),
        agent_trace=d.get("agent_trace"),
        error=d.get("error"),
    )


def load_cache():
    if not CACHE_PATH.exists():
        return {}
    return json.loads(CACHE_PATH.read_text())


def save_cache(cache):
    cache["_signature"] = _cache_signature()
    CACHE_PATH.write_text(json.dumps(cache, indent=2, default=str))


def build_dataset(results):
    """Build a ragas EvaluationDataset list: one row-dict per SystemResult."""
    return [
        {
            "user_input": r.query,
            "reference": r.reference_answer,
            "retrieved_contexts": r.retrieved_contexts,
            "response": r.answer,
        }
        for r in results
    ]


def score_system(results):
    dataset = EvaluationDataset.from_dict(build_dataset(results))
    embeddings = LangchainEmbeddingsWrapper(
        embeddings=OllamaEmbeddings(
            model="nomic-embed-text",
            base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"),
        )
    )
    scorer = evaluate(
        dataset,
        metrics=[metric for _, metric in METRICS],
        # RAG_JUDGE_MODEL: eval-only judge model (defaults to the query model);
        # plan §2.1 sanctions a cheap model for the judge role.
        llm=llm_factory(
            model=os.getenv("RAG_JUDGE_MODEL"),
            provider="openai",
            client=_judge_client,
        ),
        embeddings=embeddings,
        batch_size=8,
    )
    rows = scorer.scores  # list of per-sample dicts
    per_metric = {}
    for name in METRIC_NAMES:
        vals = [
            r.get(name)
            for r in rows
            if isinstance(r.get(name), (int, float)) and not math.isnan(r.get(name))
        ]
        per_metric[name] = float(sum(vals)) / len(vals) if vals else None
    per_metric["_n"] = len(rows)
    return per_metric, rows  # rows: per-sample score dicts (report per-category + kappa)


# Scoring is ~4 judge calls per row (some metrics make 2) — 150 rows × 3
# systems ≈ 1800+ calls. ragas evaluate() is sequential within a call, so
# shard each system's rows across concurrent evaluate() calls and merge the
# per-metric weighted means (exact: ragas averages rows per metric). W&B
# already handles 24-way in the query phase; 6×3 concurrent judges is safe.
_SCORE_SHARDS = 6


def _merge_scores(parts):
    total_n = sum(p["_n"] for p in parts)
    merged: dict[str, float | None] = {"_n": float(total_n)}
    for name in METRIC_NAMES:
        num = 0
        n = 0
        for p in parts:
            v = p.get(name)
            if isinstance(v, (int, float)):
                num += v * p["_n"]
                n += p["_n"]
        merged[name] = num / n if n else None
    return merged


def check_gate(scores, baseline):
    """Return (ok: bool, report: str). scores = {system: {metric: value}}."""
    report = []
    ok = True
    for system, metric in scores.items():
        for name in METRIC_NAMES:
            score = metric.get(name)
            floor = FLOORS.get(name)
            if floor is not None and score is not None and score < floor:
                ok = False
                report.append(f"{system} {name}={score:.3f} below floor {floor}")
            prev = baseline.get(system, {}).get(name)
            if prev and score is not None and (prev - score) > MAX_DROP:
                ok = False
                report.append(
                    f"{system} {name}={score:.3f} dropped {prev - score:.3f} vs baseline {prev:.3f}"
                )
    return ok, "\n".join(report) or "all metrics within gates"


async def _run_one(system: str, golden: dict, sem: asyncio.Semaphore) -> SystemResult:
    """Run one golden query through one system, bounded by the semaphore."""
    async with sem:
        if system == "baseline":
            return await asyncio.to_thread(run_baseline, golden)
        mode = AgentMode.HYBRID if system == "hybrid" else AgentMode.AGENTIC
        return await run_agent(golden, mode)


async def _run_system(
    system: str, golden_set: list[dict], concurrency: int = 12
) -> list[SystemResult]:
    """Run all golden queries for one system concurrently (seed+patch done once)."""
    _ensure_patched()
    sem = asyncio.Semaphore(concurrency)
    return await asyncio.gather(
        *(_run_one(system, golden, sem) for golden in golden_set)
    )


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--systems", nargs="+", default=None, help=" ".join(SYSTEMS))
    parser.add_argument(
        "--fast",
        action="store_true",
        help="§7.5 smoke config on the full golden set: ~15 min run (1 LLM call "
        "per generation, D13 inert, cross-encoder off). Scores are lower than "
        "production config — use for iteration, not the final baseline.",
    )
    parser.add_argument(
        "--refresh-baseline",
        action="store_true",
        help="write baseline.json instead of comparing against it",
    )
    parser.add_argument("--out", default=str(EVAL_DIR / "results.json"))
    parser.add_argument(
        "--baseline",
        default=str(BASELINE_PATH),
        help="baseline JSON to compare against (or refresh with --refresh-baseline); "
        "CI passes the committed docs/eval/baseline.json",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="run only the first N golden queries (subset; keeps production "
        "config — unlike --fast, scores stay comparable to the full run)",
    )
    parser.add_argument(
        "--smoke",
        action="store_true",
        help="§7.5 wiring check: hard-coded 3-query mini-set, no golden set "
        "dependency; asserts a score dict",
    )
    parser.add_argument(
        "--ci",
        action="store_true",
        help="§7.6 CI gate: compare against the committed docs/eval/baseline.json",
    )
    parser.add_argument(
        "--categories",
        nargs="+",
        default=None,
        help="restrict the golden set to these categories (e.g. hybrid multi-step)",
    )
    args = parser.parse_args(argv)

    golden = _SMOKE_QUERIES if args.smoke else json.loads(GOLDEN_SET_PATH.read_text())["queries"]
    if args.limit:
        golden = golden[: args.limit]
    if args.categories and not args.smoke:
        golden = [q for q in golden if q.get("category") in args.categories]
    os.environ["RAG_EVAL_LIMIT"] = str(args.limit or "")  # cache-signature scope
    if args.ci:
        args.baseline = str(BASELINE_PATH)
    systems = args.systems or list(SYSTEMS)
    concurrency = 24 if args.fast else 12
    seed()  # idempotent: DB + chroma fixtures once, then drop stale retriever UUIDs
    cache = load_cache()
    if cache.get("_signature") != _cache_signature():
        print("cached_results.json is for a different run config — re-running queries")
        cache = {}
    results_by_system = {}
    t0 = time.monotonic()
    for system in systems:
        cached = cache.get(system, [])
        if len(cached) == len(golden):
            results = [_result_from_dict(d) for d in cached]
            print(f"{system}: {len(results)} results (cached)")
        else:
            results = asyncio.run(_run_system(system, golden, concurrency))
            cache[system] = [_result_to_dict(r) for r in results]
            save_cache(cache)
            print(
                f"{system}: {len(results)} results "
                f"({time.monotonic() - t0:.0f}s elapsed)"
            )
        results_by_system[system] = results

    async def _score_all():
        tasks = []
        shard_slices = []
        for rs in results_by_system.values():
            shards = [rs[i::_SCORE_SHARDS] for i in range(_SCORE_SHARDS)]
            shards = [s for s in shards if s]
            shard_slices.append(shards)
            tasks.append(
                asyncio.gather(*(asyncio.to_thread(score_system, s) for s in shards))
            )
        parts = await asyncio.gather(*tasks)
        scores = {}
        per_query = {}
        for i, system in enumerate(results_by_system):
            scores[system] = _merge_scores([p for p, _ in parts[i]])
            rows = [None] * len(results_by_system[system])
            for k, shard in enumerate(shard_slices[i]):
                shard_rows = parts[i][k][1]  # per-sample score dicts, shard order
                for j, r in enumerate(shard_rows):
                    rows[k + j * _SCORE_SHARDS] = r
            per_query[system] = rows
        return scores, per_query

    scores, per_query = asyncio.run(_score_all())
    if args.smoke:
        missing = [s for s in systems if not (scores.get(s) or {})]
        assert not missing, f"smoke: no score dict for {missing}"
    print(f"scored in {time.monotonic() - t0:.0f}s elapsed")

    out = dict(scores)
    out["_per_query"] = per_query  # per-query metric scores for report.py
    Path(args.out).write_text(json.dumps(out, indent=2, default=str))
    print(f"wrote {args.out}")

    if args.refresh_baseline:
        Path(args.baseline).write_text(json.dumps(scores, indent=2))
        print(f"baseline refreshed -> {args.baseline}")
        print(f"total {time.monotonic() - t0:.0f}s")
        return 0

    baseline_path = Path(args.baseline)
    baseline = json.loads(baseline_path.read_text()) if baseline_path.exists() else {}
    ok, report = check_gate(scores, baseline)
    print(report)
    print(f"total {time.monotonic() - t0:.0f}s")
    if not ok:
        print("GATE FAILED")
        return 1
    print("GATE PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())