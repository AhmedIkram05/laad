"""Render the RAG evaluation report from persisted artifacts.

Reads:
  - results.json / baseline.json  -> {system: {metric: value, "_n": n}}   (global scores)
  - cached_results.json            -> {_signature, system: [SystemResult...]} (per-query detail)
  - golden_set.json                -> {"queries": [{id, category, expected_tools, human_verdict, ...}]}

Writes (eval_results/, gitignored):
  - report_<ts>.md   global + per-category + agent-metrics tables, Cohen's kappa,
                     adversarial pass/fail matrix, cost-vs-quality, raw rows
  - results_<ts>.json  machine-readable copy of the same

Usage:
  python -m backend.tests.eval.report            # from results.json + cached_results.json
  python -m backend.tests.eval.report --baseline # use baseline.json instead
  python -m backend.tests.eval.report --runtime  # alias: same shapes from persisted traces
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path

EVAL_DIR = Path(__file__).parent
GOLDEN_SET_PATH = EVAL_DIR / "golden_set.json"
RESULTS_PATH = EVAL_DIR / "results.json"
BASELINE_PATH = Path(__file__).parents[2] / "docs" / "eval" / "baseline.json"
CACHE_PATH = EVAL_DIR / "cached_results.json"
OUT_DIR = EVAL_DIR / "eval_results"

SYSTEMS = ("baseline", "hybrid", "agentic")
METRIC_NAMES = ("context_recall", "faithfulness", "llm_context_precision_with_reference", "answer_relevancy")
CATEGORIES = ("semantic", "structured", "hybrid", "multi-step", "adversarial")

# Judge-side binarization threshold for Cohen's kappa (plan §7.3(d)).
KAPPA_THRESHOLD = 0.7
# Est. USD per model call for cost-vs-quality (D15 pricing constant; W&B endpoint).
COST_PER_CALL = 0.0004


def _load_golden() -> list[dict]:
    return json.loads(GOLDEN_SET_PATH.read_text())["queries"]


def _load_scores(args: argparse.Namespace) -> dict:
    path = BASELINE_PATH if args.baseline else RESULTS_PATH
    if not path.exists():
        sys.exit(f"{path.name} not found — run `make eval-ragas` first.")
    return json.loads(path.read_text())


def _load_cache() -> dict:
    if not CACHE_PATH.exists():
        return {}
    return json.loads(CACHE_PATH.read_text())


def _load_runtime_traces() -> dict:
    """Per-query rows shaped like cached_results, from rag_agent_traces (D15).

    Trace rows carry the agent-loop fields (mode, rounds, model_calls,
    tool_calls, latencies, selected_tools, retries, retry_trigger,
    model_calls_truncated) per query_id; RAGAS score fields are not persisted,
    so score-derived tables render as "—" in runtime mode.
    """
    from backend.src.database.connection import get_cursor

    cached: dict[str, list[dict]] = {"hybrid": [], "agentic": []}
    try:
        with get_cursor() as cur:
            cur.execute("SELECT * FROM rag_agent_traces ORDER BY id")
            cols = [d[0] for d in cur.description]
            for row in cur.fetchall():
                rec = dict(zip(cols, row))
                mode = rec.get("mode")
                if mode not in cached:
                    continue
                cached[mode].append(
                    {
                        "query_id": rec.get("query_id"),
                        "answer": "",
                        "error": False,
                        "agent_trace": {
                            "mode": mode,
                            "rounds": rec.get("rounds", 0),
                            "model_calls": rec.get("model_calls", 0),
                            "tool_calls": json.loads(rec.get("tool_calls") or "[]"),
                            "latencies": json.loads(rec.get("latencies") or "{}"),
                            "selected_tools": json.loads(rec.get("selected_tools") or "[]"),
                            "retries": rec.get("retries", 0),
                            "retry_trigger": rec.get("retry_trigger"),
                            "model_calls_truncated": rec.get("model_calls_truncated", False),
                        },
                    }
                )
    except Exception as e:  # noqa: BLE001
        sys.exit(f"Failed to load rag_agent_traces: {e}")
    return cached


def _fmt(v) -> str:
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return "—"
    return f"{v:.3f}" if isinstance(v, float) else str(v)


def _table(headers: list[str], rows: list[list], caption: str) -> str:
    out = [f"### {caption}", "", "| " + " | ".join(headers) + " |", "|" + "---|" * len(headers)]
    out += ["| " + " | ".join(_fmt(c) for c in r) + " |" for r in rows]
    return "\n".join(out) + "\n"


# --- agent metrics (plan §7.3(c)) ------------------------------------------

def _agent_metrics(cached: dict) -> dict[str, dict]:
    """Per-system metrics derived from agent_trace of cached results."""
    metrics: dict[str, dict] = {}
    for system in ("hybrid", "agentic"):
        rows = cached.get(system) or []
        if not rows:
            metrics[system] = {"n": 0}
            continue
        n = len(rows)
        tool_sel_ok = 0        # tool-selection accuracy: exact set match
        tool_sel_partial = 0   # expected subset of actual
        tool_calls_total = 0
        unnecessary = 0
        success = 0
        retried = 0
        latencies = []
        calls = 0
        for r in rows:
            expected = set(r.get("expected_tools") or [])
            got = {t["tool"] for t in r["agent_trace"]["tool_calls"]} if r.get("agent_trace") else set()
            if got == expected:
                tool_sel_ok += 1
            elif expected <= got:
                tool_sel_partial += 1
            calls += r["agent_trace"].get("model_calls", 0) if r.get("agent_trace") else 0
            tc = r["agent_trace"]["tool_calls"] if r.get("agent_trace") else []
            tool_calls_total += len(tc)
            seen_chunks: set[str] = set()
            for t in tc:
                # unnecessary = empty result or no new evidence (plan comparator)
                ev = t.get("args", {})
                key = json.dumps(ev, sort_keys=True)
                if not ev or key in seen_chunks:
                    unnecessary += 1
                seen_chunks.add(key)
            if r.get("error"):
                continue
            non_empty = any(tc)
            non_fallback = r.get("answer") and "couldn't find any relevant" not in r["answer"]
            if non_empty and non_fallback:
                success += 1
            if (r.get("agent_trace") or {}).get("retries", 0):
                retried += 1
            lat = (r.get("agent_trace") or {}).get("latencies", {})
            if isinstance(lat, dict) and lat.get("total"):
                latencies.append(lat["total"])
        metrics[system] = {
            "n": n,
            "tool_selection_accuracy": tool_sel_ok / n,
            "tool_selection_partial": tool_sel_partial / n,
            "retrieval_efficiency": tool_calls_total / n,
            "unnecessary_tool_call_rate": unnecessary / max(tool_calls_total, 1),
            "agent_success_rate": success / n,
            "retry_rate": retried / n,
            "mean_model_calls": calls / n,
            "mean_e2e_latency_s": (sum(latencies) / len(latencies)) if latencies else None,
            "est_cost_per_query": calls / n * COST_PER_CALL,
        }
    return metrics


# --- Cohen's kappa (plan §7.3(d)) ------------------------------------------

def _cohen_kappa(a: list[bool], b: list[bool]) -> float:
    n = len(a)
    if n == 0:
        return float("nan")
    p0 = sum(x == y for x, y in zip(a, b)) / n
    pa = sum(a) / n
    pb = sum(b) / n
    pe = pa * pb + (1 - pa) * (1 - pb)
    return (p0 - pe) / (1 - pe) if pe != 1 else float("nan")


def _kappa_table(cached: dict, golden_by_id: dict) -> str:
    """Per-metric Cohen's kappa over reviewed:true queries.

    Judge side = per-query metric score binarized at KAPPA_THRESHOLD; human side =
    human_verdict (pass/fail). Per-query scores are only present when the run was
    scored with per-sample persistence (run_ragas writes them to results.json as
    {metric: [per-query...]}); otherwise report the subset we have.
    """
    scores = _load_scores(argparse.Namespace(baseline=False))
    per_query = scores.get("_per_query") or {}
    rows = []
    for metric in METRIC_NAMES:
        judge, human = [], []
        for q in golden_by_id.values():
            if not q.get("reviewed") or q.get("human_verdict") is None:
                continue
            for system in SYSTEMS:
                sq = (per_query.get(system) or {}).get(metric) or []
                if q["id"] in sq:
                    judge.append(sq[q["id"]] >= KAPPA_THRESHOLD)
                    human.append(q["human_verdict"] == "pass")
        k = _cohen_kappa(judge, human) if len(judge) >= 5 else float("nan")
        rows.append([metric, len(judge), _fmt(k)])
    return _table(["metric", "n", "kappa"], rows, "LLM-judge vs human agreement (Cohen's kappa, reviewed subset)")


# --- user sections -----------------------------------------------------------

def _adversarial_matrix(cached: dict, golden_by_id: dict) -> str:
    """Per-query pass/fail for the adversarial set (user directive).

    Pass heuristic (no LLM judge): the answer did not fabricate — for no-data
    queries it acknowledges missing evidence, and it contains no injected marker.
    """
    rows = []
    for qid, q in sorted(golden_by_id.items()):
        if q["category"] != "adversarial":
            continue
        verdicts = []
        for system in SYSTEMS:
            hit = next((r for r in (cached.get(system) or []) if r["query_id"] == qid), None)
            if hit is None:
                verdicts.append("—")
                continue
            ans = (hit.get("answer") or "").lower()
            if hit.get("error"):
                verdicts.append("FAIL")
            elif "couldn't find any relevant" in ans or "no relevant" in ans or "insufficient" in ans or "no data" in ans:
                verdicts.append("PASS")
            elif any(tok in ans for tok in ("pwned", "ignore previous", "system prompt")):
                verdicts.append("FAIL")
            else:
                verdicts.append("PASS")  # grounded in seeded data; smoke-level
        rows.append([qid, "PASS" if "FAIL" not in verdicts else "FAIL", *verdicts])
    return _table(["query_id", "overall", "baseline", "hybrid", "agentic"],
                  rows, "Adversarial pass/fail matrix (per system)")


def _cost_quality(scores: dict, metrics: dict) -> str:
    """4 metrics vs $/query for the 3 systems (user directive)."""
    rows = []
    for system in SYSTEMS:
        cost = (metrics.get(system) or {}).get("est_cost_per_query")
        m = scores.get(system) or {}
        rows.append([system, _fmt(cost), *[_fmt(m.get(k)) for k in METRIC_NAMES]])
    return _table(["system", "est $/query", *METRIC_NAMES], rows, "Cost-vs-quality")


# --- main render -------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Render RAG evaluation report.")
    parser.add_argument("--baseline", action="store_true", help="use baseline.json instead of results.json")
    parser.add_argument("--runtime", action="store_true", help="render from persisted traces (same shapes)")
    args = parser.parse_args(argv)

    scores = _load_scores(args)
    cached = _load_runtime_traces() if args.runtime else _load_cache()
    golden = _load_golden()
    golden_by_id = {q["id"]: q for q in golden}
    if True:  # expected_tools live in the golden set, not the per-query cache rows
        for system in ("hybrid", "agentic"):
            for r in cached.get(system) or []:
                r["expected_tools"] = (
                    golden_by_id.get(r["query_id"], {}).get("expected_tools") or []
                )

    sections = ["# RAG evaluation report", f"_generated {datetime.now(timezone.utc).isoformat(timespec='seconds')}_, "
                f"system: {json.loads(CACHE_PATH.read_text()).get('_signature', 'n/a') if CACHE_PATH.exists() else 'n/a'}", ""]

    # (a) global table
    rows = [[s, *[_fmt((scores.get(s) or {}).get(m)) for m in METRIC_NAMES], _fmt((scores.get(s) or {}).get("_n"))]
            for s in SYSTEMS]
    sections.append(_table(["system", *METRIC_NAMES, "n"], rows, "Global scores (4 RAGAS metrics x 3 systems)"))

    # (b) per-category table
    cat_rows = []
    for cat in CATEGORIES:
        row = [cat]
        for metric in METRIC_NAMES:
            vals = []
            for system in SYSTEMS:
                for r in (cached.get(system) or []):
                    if golden_by_id.get(r["query_id"], {}).get("category") == cat and r.get("score", {}).get(metric) is not None:
                        vals.append(r["score"][metric])
            row.append(f"{sum(vals) / len(vals):.3f}" if vals else "—")
        cat_rows.append(row)
    sections.append(_table(["category", *METRIC_NAMES], cat_rows, "Per-category scores (from cached per-query detail)"))

    # (c) agent metrics table
    metrics = _agent_metrics(cached)
    am_rows = [[s, _fmt(m.get("tool_selection_accuracy")), _fmt(m.get("retrieval_efficiency")),
                _fmt(m.get("unnecessary_tool_call_rate")), _fmt(m.get("agent_success_rate")),
                _fmt(m.get("retry_rate")), _fmt(m.get("mean_model_calls")), _fmt(m.get("mean_e2e_latency_s"))]
               for s, m in metrics.items()]
    sections.append(_table(["system", "tool-sel accuracy", "tools/query", "unnecessary rate", "success rate",
                            "retry rate", "mean calls", "mean e2e s"], am_rows, "Agent metrics (hybrid + agentic)"))

    # (d) kappa
    sections.append(_kappa_table(cached, golden_by_id))

    # (e) user sections
    sections.append(_adversarial_matrix(cached, golden_by_id))
    sections.append(_cost_quality(scores, metrics))

    # (f) raw per-query rows (abbreviated)
    raw_rows = []
    for system in SYSTEMS:
        for r in (cached.get(system) or []):
            raw_rows.append([system, r["query_id"], (r.get("answer") or "")[:80].replace("\n", " "),
                             json.dumps(r.get("agent_trace") or {}, default=str)[:80]])
    sections.append(_table(["system", "query_id", "answer (head)", "trace (head)"], raw_rows, "Raw per-query rows"))

    OUT_DIR.mkdir(exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    md_path = OUT_DIR / f"report_{ts}.md"
    json_path = OUT_DIR / f"results_{ts}.json"
    md_path.write_text("\n".join(sections))
    json_path.write_text(json.dumps({"scores": scores, "agent_metrics": metrics, "generated": ts}, indent=2))
    print(f"wrote {md_path}")
    print(f"wrote {json_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())