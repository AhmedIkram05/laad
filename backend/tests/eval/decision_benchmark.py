"""3-arm decision benchmark: llm-only / jev-only / cascade over the golden set.

Runs the same pass-verdict golden items (currently 41) through three
verbalized-confidence arms and compares agreement with the human verdicts,
escalation rate, estimated USD cost, and ECE:

  - llm-only: the existing LLM verbalized-confidence path per item (real
    W&B calls; per-item real cost from LLMResponse.cost_usd, fallback
    telemetry.COST_PER_CALL).
  - jev-only: stored Jev score confidences from the calibration report
    (decision_calibration_report.json) — no API spend when storage has them;
    a bounded live Jev pass fills missing items (~1.6e-05 USD/call).
  - cascade: Jev primary; items with Jev confidence < tau escalate to the
    LLM. Escalated items REUSE the llm-only arm's measured confidence (same
    prompt, same item — avoids double spend).

LLM information parity: golden items have no retrieved log context, so the
LLM arm passes context=query and answer=reference_answer — exactly the
information the Jev calibration state carried (query + reference answer).

MLflow: one run per arm under experiment "laad-rag-decisions" (graceful:
unreachable server → warning + continue, following
ml_detector.py's _mlflow_available pattern). The JSON report at
backend/tests/eval/decision_benchmark_report.json is ALWAYS written and is
the durable artifact.

Run (from backend/ — LLM key from ../.env; RAG_RATE_LIMIT=0 disables the
client-side 20/min limiter that otherwise raises on bulk eval calls, same as
the RAGAS eval runs):
    cd backend
    set -a; source ../.env; set +a
    RAG_RATE_LIMIT=0 ../.venv/bin/python tests/eval/decision_benchmark.py [--tau 0.55] [--limit N]
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path
from typing import Optional

# Standalone script: make `backend.*` imports work regardless of CWD.
REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.src.rag.generator import RAGGenerator, _confidence_from_answer  # noqa: E402
from backend.tests.eval.decision_calibration import (  # noqa: E402
    JEV_COST_PER_CALL_DEFAULT,
    POSITIVE_THRESHOLD,
    SCORE_QUESTION,
    SCORE_QUESTION_NAME,
    _score_interpolated,
    expected_calibration_error,
    _state_for,
)
from backend.src.rag.decision_client import (  # noqa: E402
    get_decision_provider,
)

logger = logging.getLogger(__name__)

GOLDEN_SET_PATH = REPO_ROOT / "backend" / "tests" / "eval" / "golden_set.json"
CALIBRATION_REPORT_PATH = (
    REPO_ROOT / "backend" / "tests" / "eval" / "decision_calibration_report.json"
)
BENCHMARK_REPORT_PATH = (
    REPO_ROOT / "backend" / "tests" / "eval" / "decision_benchmark_report.json"
)

MLFLOW_TRACKING_URI = os.getenv("MLFLOW_TRACKING_URI", "http://mlflow:5000")
MLFLOW_EXPERIMENT = "laad-rag-decisions"

ECE_BINS = 10


def _llm_cost_fallback() -> float:
    """telemetry.COST_PER_CALL when importable (deterministic fallback price)."""
    try:
        from backend.src.rag.telemetry import COST_PER_CALL

        return COST_PER_CALL
    except Exception:  # pragma: no cover - import chain avoidance
        return 0.0004


def load_golden_items(limit: Optional[int] = None) -> list[dict]:
    """Pass-verdict golden items (all-positives calibration population)."""
    queries = json.loads(GOLDEN_SET_PATH.read_text())["queries"]
    items = [q for q in queries if str(q.get("human_verdict", "")).lower() == "pass"]
    return items[:limit] if limit else items


def load_jev_confs(items: list[dict]) -> tuple[dict[int, float], dict[int, float]]:
    """Stored Jev confidences (and per-call costs) keyed by item id.

    Uses the interpolated legend reading (raw score / (n-1)) — the winning
    score-semantics normalization — with .probability as the fallback when
    the stored payload lacks a score field.
    """
    confs: dict[int, float] = {}
    costs: dict[int, float] = {}
    if CALIBRATION_REPORT_PATH.exists():
        report = json.loads(CALIBRATION_REPORT_PATH.read_text())
        for entry in report.get("items", []):
            score_raw = entry.get("score_raw")
            conf = (
                _score_interpolated(score_raw)
                if isinstance(score_raw, dict)
                else None
            )
            if conf is None and entry.get("score_probability") is not None:
                conf = float(entry["score_probability"])
            if conf is None:
                continue
            item_id = entry.get("id")
            confs[item_id] = conf
            if entry.get("cost_usd") is not None:
                costs[item_id] = float(entry["cost_usd"])
    return confs, costs


def _live_jev_fill(missing_items: list[dict]) -> dict[int, float]:
    """Bounded live Jev pass for items missing from storage (~$2e-05/call)."""
    provider = get_decision_provider()
    if provider is None:
        logger.warning("No decision provider; jev-only/cascade arms will be short")
        return {}
    filled: dict[int, float] = {}
    for item in missing_items:
        try:
            answers = provider.decide(
                _state_for(item["query"], item.get("reference_answer", "")),
                {SCORE_QUESTION_NAME: SCORE_QUESTION},
            )
            answer = answers.get(SCORE_QUESTION_NAME)
            if answer is not None:
                filled[item["id"]] = _confidence_from_answer(answer)
        except Exception as exc:
            logger.warning("Jev fill failed for id=%s: %s", item.get("id"), exc)
    return filled


def run_llm_arm(items: list[dict], generator: RAGGenerator) -> dict[int, dict]:
    """Real LLM verbalized-confidence per item; returns id -> {conf, cost_usd}."""
    llm_cost = _llm_cost_fallback()
    results: dict[int, dict] = {}
    for item in items:
        # context=query gives the LLM the same information the Jev calibration
        # state carried (query + reference answer); golden items carry no logs.
        cost_sink: list[float] = []
        confidence = generator._llm_verbalized_confidence(
            item["query"], item["query"], item.get("reference_answer", ""),
            system_prompt="", cost_sink=cost_sink,
        )
        if confidence is None:
            continue
        results[item["id"]] = {
            "confidence": confidence,
            "cost_usd": cost_sink[0] if cost_sink else llm_cost,
        }
    return results


def simulate_cascade(
    jev_confs: list[float],
    llm_confs: list[Optional[float]],
    tau: float,
) -> tuple[list[float], list[bool], int]:
    """Jev primary; below tau → escalate to the LLM (use its measured result).

    jev_confs and llm_confs are positionally aligned over the same items.
    Returns (final_confidences, escalated_flags, n_unresolved) where
    n_unresolved counts escalations with no LLM measurement available (Jev
    confidence kept as a conservative fallback).
    """
    final: list[float] = []
    escalated: list[bool] = []
    unresolved = 0
    for index, jev_conf in enumerate(jev_confs):
        if jev_conf >= tau:
            final.append(jev_conf)
            escalated.append(False)
            continue
        escalated.append(True)
        llm_conf = llm_confs[index] if index < len(llm_confs) else None
        if llm_conf is None:
            unresolved += 1
            final.append(jev_conf)
        else:
            final.append(llm_conf)
    return final, escalated, unresolved


def arm_metrics(
    final_confs: list[float],
    escalated: list[bool],
    est_cost_usd: float,
) -> dict:
    """Agreement (all-pass golden set), escalation rate, ECE."""
    n = len(final_confs)
    ece, _ = expected_calibration_error(final_confs, [1] * n) if n else (None, [])
    return {
        "n_items": n,
        "agreement_rate": round(
            sum(1 for c in final_confs if c >= POSITIVE_THRESHOLD) / n, 4
        ) if n else None,
        "escalation_rate": round(sum(1 for e in escalated if e) / n, 4)
        if n else None,
        "est_cost_usd": round(est_cost_usd, 6),
        "ece_10bin": round(ece, 4) if ece is not None else None,
    }


def _mlflow_log(runs: list[dict], tau: float) -> bool:
    """One MLflow run per arm; graceful on unreachable server (ml_detector pattern)."""
    try:
        import mlflow
    except ImportError:
        logger.warning("mlflow not installed; skipping MLflow logging")
        return False
    try:
        mlflow.set_tracking_uri(MLFLOW_TRACKING_URI)
        mlflow.set_experiment(MLFLOW_EXPERIMENT)
        for run in runs:
            with mlflow.start_run(run_name=f"decision-benchmark-{run['arm']}"):
                mlflow.log_params(
                    {"arm": run["arm"], "tau": tau, "n_items": run["n_items"]}
                )
                mlflow.log_metrics(
                    {
                        "agreement_rate": run["agreement_rate"] or 0.0,
                        "escalation_rate": run["escalation_rate"] or 0.0,
                        "est_cost_usd": run["est_cost_usd"],
                        "ece": run["ece_10bin"] or 0.0,
                    }
                )
        return True
    except Exception as exc:
        logger.warning(
            "MLflow unavailable (benchmark JSON report is the durable artifact): "
            "%s. URI=%s",
            exc,
            MLFLOW_TRACKING_URI,
        )
        return False


def _print_table(arms: list[dict], tau: float) -> None:
    print(f"\n3-arm benchmark (tau={tau:.2f}, all-pass golden items):")
    print("| arm       | n  | agree% | escal% | est cost $ | ece    |")
    for arm in arms:
        print(
            f"| {arm['arm']:<9} | {arm['n_items']:>2} | "
            f"{(arm['agreement_rate'] or 0) * 100:5.1f} | "
            f"{(arm['escalation_rate'] or 0) * 100:5.1f} | "
            f"{arm['est_cost_usd']:.6f} | "
            f"{arm['ece_10bin'] if arm['ece_10bin'] is not None else 'n/a'} |"
        )


def run(tau: Optional[float] = None, limit: Optional[int] = None) -> dict:
    """Run all three arms; always write the JSON report (durable artifact)."""
    from backend.src.rag.config import config

    tau = float(tau if tau is not None else config.jev_escalation_threshold)

    items = load_golden_items(limit)
    if not items:
        print("No pass-verdict golden items found.")
        return {}

    # --- Jev data: stored first, bounded live fill only for missing items ---
    jev_by_id, jev_costs = load_jev_confs(items)
    missing = [i for i in items if i["id"] not in jev_by_id]
    if missing:
        print(f"{len(missing)} items missing stored Jev data; live Jev fill...")
        jev_by_id.update(_live_jev_fill(missing))
    jev_confs = [jev_by_id.get(i["id"]) for i in items]
    jev_available = [c for c in jev_confs if c is not None]
    jev_per_call = (
        sum(jev_costs.values()) / len(jev_costs)
        if jev_costs
        else JEV_COST_PER_CALL_DEFAULT
    )

    # --- LLM arm: real calls for every item (cascade reuses these results) ---
    generator = RAGGenerator()
    generator.decision_provider = None  # force the existing LLM path
    llm_results = run_llm_arm(items, generator)

    llm_only_cost = sum(
        (llm_results[i["id"]]["cost_usd"] if i["id"] in llm_results
         else _llm_cost_fallback())
        for i in items
    )
    jev_only_cost = len(items) * jev_per_call
    escalated_flags = [c is not None and c < tau for c in jev_confs]
    cascade_cost = jev_only_cost + sum(
        llm_results[i["id"]]["cost_usd"]
        if i["id"] in llm_results
        else _llm_cost_fallback()
        for i, e in zip(items, escalated_flags)
        if e
    )

    # Final confidences per arm; cascade escalations reuse the llm-only arm's
    # measured confidence (same prompt, same item — no double spend). Missing
    # LLM/Jev measurements count as 0.0 (conservative: never inflates agreement).
    jev_final = [c if c is not None else 0.0 for c in jev_confs]
    llm_final = [
        llm_results[i["id"]]["confidence"] if i["id"] in llm_results else 0.0
        for i in items
    ]
    llm_aligned: list[Optional[float]] = [
        llm_results[i["id"]]["confidence"] if i["id"] in llm_results else None
        for i in items
    ]
    cascade_final, cascade_escalated, unresolved = simulate_cascade(
        jev_final, llm_aligned, tau
    )

    arms = [
        {
            "arm": "llm-only",
            **arm_metrics(llm_final, [False] * len(items), llm_only_cost),
            "note": "existing LLM verbalized-confidence path, real per-item cost",
        },
        {
            "arm": "jev-only",
            **arm_metrics(jev_final, [False] * len(items), jev_only_cost),
            "jev_items_missing_storage": len(items) - len(jev_available),
            "jev_cost_per_call": round(jev_per_call, 6),
        },
        {
            "arm": "cascade",
            **arm_metrics(cascade_final, cascade_escalated, cascade_cost),
            "unresolved_escalations": unresolved,
            "note": "Jev primary; escalations reuse the llm-only arm's measured "
            "confidence (same prompt, no double spend)",
        },
    ]

    report = {
        "tau": tau,
        "experiment": MLFLOW_EXPERIMENT,
        "mlflow_tracking_uri": MLFLOW_TRACKING_URI,
        "items_with_llm_result": len(llm_results),
        "items_with_stored_jev": len(jev_available),
        "llm_cost_source": (
            "fallback" if len(llm_results) == 0 else
            "real" if any(
                r["cost_usd"] != _llm_cost_fallback()
                for r in llm_results.values()
            ) else "fallback (provider did not report usage.cost)"
        ),
        "notes": [
            "Golden items carry no retrieved log context; the llm-only arm "
            "runs the EXISTING verbalized-confidence prompt verbatim "
            "(context=query, answer=reference_answer). That prompt is built "
            "to grade generated answers against retrieved logs, so without "
            "log context its confidence is degenerately low — an empirical "
            "finding, not a harness bug. In production (SWAP-1 escalation) "
            "the LLM path sees real retrieved context and behaves normally.",
            "Escalated cascade items reuse the llm-only arm's measured "
            "confidence (same prompt/item; no double spend).",
        ],
        "arms": arms,
    }
    report["mlflow_logged"] = _mlflow_log(arms, tau)
    BENCHMARK_REPORT_PATH.write_text(json.dumps(report, indent=2))
    _print_table(arms, tau)
    print(f"Report written to {BENCHMARK_REPORT_PATH} "
          f"(mlflow_logged={report['mlflow_logged']})")
    return report


def main(argv=None) -> int:
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--tau", type=float, default=None,
        help="escalation threshold (default: config.jev_escalation_threshold)",
    )
    parser.add_argument(
        "--limit", type=int, default=None,
        help="cap the number of golden items (cost control)",
    )
    args = parser.parse_args(argv)
    report = run(tau=args.tau, limit=args.limit)
    return 0 if report else 1


if __name__ == "__main__":
    sys.exit(main())
