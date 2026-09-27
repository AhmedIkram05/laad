"""Decision calibration harness: Jev noul vs golden-set human verdicts.

For each golden-set item (backend/tests/eval/golden_set.json) asks Jev ONE
decision call with TWO questions (cost is call-level, so the second question
is essentially free):
  - noul "reference_correct" — "is this reference answer correct for this
    query?" (state = query + reference_answer truncated to ~2k chars)
  - score "answer_confidence" — same 10-level criteria the generator uses for
    verbalized confidence, so the stored raw payloads support the offline
    score-semantics comparison (top-level certainty vs interpolated position).

Outputs (printed AND written to backend/tests/eval/decision_calibration_report.json):
  - confusion matrix (TP/FP/TN/FN at threshold 0.5), accuracy/precision/recall
  - Expected Calibration Error (10 bins)
  - per-item stored data: noul probability + raw payload, score probability +
    raw payload (score/legend/probabilities), per-call cost
  - score-semantics comparison: .probability (top-level certainty) vs
    raw["score"]/(len(levels)-1) (interpolated position) — ECE, mean, min,
    accuracy@0.5 for both normalizations
  - tau sweep (also via --sweep, offline from the stored report): for τ in
    0.50..0.95 step 0.05 the escalation rate, agreement rate and estimated
    cascade/LLM-only cost ratio
  - per-call and total USD cost, skipped-item counts

Verdict mapping (inspected golden set): the file currently uses
human_verdict="pass" (reviewed, positive) and null (unreviewed). Any
"correct"-family value counts positive, any "incorrect"/"irrelevant"-family
value counts negative, null/unknown values are skipped and counted. NOTE: a
golden set with only positives cannot produce FP/TN — accuracy equals recall
and precision is undefined; the report records the verdict distribution so
the skew is explicit.

Run (from backend/ — the OpenRouter key comes from ../.env via TYPESAFE_API_KEY):
    cd backend
    set -a; source ../.env; set +a
    RAG_DECISION_PROVIDER=jev ../.venv/bin/python tests/eval/decision_calibration.py

Offline re-analysis only (no key needed, reads the stored report):
    ../.venv/bin/python tests/eval/decision_calibration.py --sweep

Docker-free; 50 decision calls at ~1.6e-05 USD each (~0.0007 total).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Optional

# Standalone script: make `backend.*` imports work regardless of CWD.
REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.src.rag.decision_client import (  # noqa: E402
    DecisionQuestion,
    get_decision_provider,
)

GOLDEN_SET_PATH = REPO_ROOT / "backend" / "tests" / "eval" / "golden_set.json"
REPORT_PATH = REPO_ROOT / "backend" / "tests" / "eval" / "decision_calibration_report.json"

POSITIVE_THRESHOLD = 0.5
STATE_MAX_CHARS = 2000
ECE_BINS = 10

# Mirrors telemetry.COST_PER_CALL (not imported: the calibration script must
# stay standalone and docker-free, without the database.connection import).
LLM_COST_PER_CALL = 0.0004
# Measured Jev cost per decision call (falls back to the stored report's
# cost_usd_per_call_mean when present).
JEV_COST_PER_CALL_DEFAULT = 0.000016

TAU_VALUES = [round(0.5 + 0.05 * i, 2) for i in range(10)]  # 0.50 .. 0.95

POSITIVE_VERDICTS = {"pass", "correct", "relevant", "yes", "good", "accurate"}
NEGATIVE_VERDICTS = {"fail", "incorrect", "irrelevant", "no", "bad", "wrong"}

QUESTION_NAME = "reference_correct"
QUESTION = DecisionQuestion(
    name=QUESTION_NAME,
    type="noul",
    instructions=(
        "Is this reference answer correct for this query? Answer yes if the "
        "reference answer is accurate, complete and appropriate for the query; "
        "answer no if it is wrong, misleading, incomplete or does not address "
        "the query."
    ),
)

# Same 10-level legend the generator uses for verbalized confidence
# (generator._CONFIDENCE_LEVELS, kept local so this script never imports the
# generator's retriever/chromadb dependency chain).
CONFIDENCE_LEVELS = [f"{level / 10:.1f}" for level in range(10)]
SCORE_QUESTION_NAME = "answer_confidence"
SCORE_QUESTION = DecisionQuestion(
    name=SCORE_QUESTION_NAME,
    type="score",
    instructions=(
        "Rate the likelihood that the reference answer is correct and "
        "appropriate for the query. A high level means every claim in the "
        "answer is accurate, complete and appropriate; a low level means "
        "claims are unsupported, inferred or wrong."
    ),
    criteria=CONFIDENCE_LEVELS,
)


def verdict_to_label(verdict: object) -> Optional[int]:
    """Map a human_verdict to 1 (positive) / 0 (negative); None = skip."""
    if verdict is None:
        return None
    value = str(verdict).strip().lower()
    if value in POSITIVE_VERDICTS:
        return 1
    if value in NEGATIVE_VERDICTS:
        return 0
    return None


def _state_for(query: str, reference_answer: str) -> str:
    state = f"Query:\n{query}\n\nReference answer:\n{reference_answer}"
    return state[:STATE_MAX_CHARS]


def expected_calibration_error(
    probabilities: list[float], labels: list[int]
) -> tuple[float, list[dict]]:
    """ECE over 10 equal-width bins of predicted probability."""
    bins = [
        {"bin_low": i / ECE_BINS, "bin_high": (i + 1) / ECE_BINS, "n": 0,
         "conf_sum": 0.0, "correct_sum": 0.0}
        for i in range(ECE_BINS)
    ]
    for prob, label in zip(probabilities, labels):
        index = min(int(prob * ECE_BINS), ECE_BINS - 1)
        bins[index]["n"] += 1
        bins[index]["conf_sum"] += prob
        bins[index]["correct_sum"] += float(label == 1)
    total = len(probabilities)
    ece = 0.0
    for bin_data in bins:
        if bin_data["n"]:
            bin_acc = bin_data["correct_sum"] / bin_data["n"]
            bin_conf = bin_data["conf_sum"] / bin_data["n"]
            ece += (bin_data["n"] / total) * abs(bin_acc - bin_conf)
            bin_data["mean_prob"] = round(bin_conf, 4)
            bin_data["mean_label"] = round(bin_acc, 4)
        else:
            bin_data["mean_prob"] = None
            bin_data["mean_label"] = None
        del bin_data["conf_sum"]
        del bin_data["correct_sum"]
    return ece, bins


# ---------------------------------------------------------------------------
# Offline analytics (no API spend): score-semantics comparison + tau sweep.
# ---------------------------------------------------------------------------


def _score_interpolated(score_raw: dict) -> Optional[float]:
    """Normalization (b): raw score position / (len(levels) - 1) -> 0-1."""
    score = score_raw.get("score")
    if not isinstance(score, (int, float)):
        return None
    n_levels = len(CONFIDENCE_LEVELS)
    if n_levels <= 1:
        return None
    return max(0.0, min(1.0, float(score) / (n_levels - 1)))


def score_semantics(items: list[dict]) -> Optional[dict]:
    """Compare the two score-type normalizations against pass verdicts.

    (a) score_probability — DecisionAnswer.probability: certainty of the TOP
        legend level (max of the level-probabilities).
    (b) interpolated — raw["score"] / (len(levels) - 1): continuous position
        on the legend scale normalized to 0-1.

    With an all-positive golden set, calibration means the predictions should
    sit near 1.0; ECE lower = better calibrated, accuracy@0.5 = agreement.
    """
    tops, interps, labels = [], [], []
    for item in items:
        if item.get("label") != 1:
            continue  # negatives: none exist in the current golden set
        if item.get("score_probability") is not None:
            tops.append(float(item["score_probability"]))
            labels.append(1)
            interp = _score_interpolated(item.get("score_raw") or {})
            interps.append(interp if interp is not None else 0.0)
    if not tops:
        return None
    ece_top, _ = expected_calibration_error(tops, labels)
    ece_interp, _ = expected_calibration_error(interps, labels)

    def _stats(confs: list[float], ece: float) -> dict:
        return {
            "n": len(confs),
            "mean_conf": round(sum(confs) / len(confs), 4),
            "min_conf": round(min(confs), 4),
            "max_conf": round(max(confs), 4),
            "accuracy_at_0.5": round(
                sum(1 for c in confs if c >= POSITIVE_THRESHOLD) / len(confs), 4
            ),
            "ece_10bin": round(ece, 4),
        }

    return {
        "note": (
            "All golden labels positive: ECE lower = better calibrated "
            "(predictions should sit near 1.0); accuracy@0.5 = agreement "
            "with pass verdicts."
        ),
        "top_level_certainty_probability": _stats(tops, ece_top),
        "interpolated_score_normalized": _stats(interps, ece_interp),
    }


def tau_sweep_table(
    confidences: list[float],
    jev_cost: float,
    llm_cost: float,
) -> list[dict]:
    """Offline tau sweep: escalation / agreement / cost-ratio per threshold.

    All-positives golden set, so agreement rate = fraction of items with
    Jev confidence >= tau. Cost model: cascade = n Jev calls + (escalated)
    LLM calls; llm-only = n LLM calls.
    """
    n = len(confidences)
    table = []
    for tau in TAU_VALUES:
        escalated = sum(1 for c in confidences if c < tau)
        escalation_rate = escalated / n if n else 0.0
        agreement_rate = (n - escalated) / n if n else 0.0
        cascade_cost = n * jev_cost + escalated * llm_cost
        llm_only_cost = n * llm_cost
        table.append(
            {
                "tau": tau,
                "escalated_items": escalated,
                "escalation_rate": round(escalation_rate, 4),
                "agreement_rate": round(agreement_rate, 4),
                "cascade_est_cost_usd": round(cascade_cost, 6),
                "llm_only_est_cost_usd": round(llm_only_cost, 6),
                "cost_ratio_cascade_vs_llm": round(
                    cascade_cost / llm_only_cost, 4
                ) if llm_only_cost else None,
            }
        )
    return table


def _append_offline_analytics(report: dict) -> dict:
    """Attach score-semantics comparison + tau sweep to a report (in place)."""
    items = report.get("items", [])
    semantics = score_semantics(items)
    if semantics is not None:
        report["score_semantics"] = semantics
    signals = {
        "noul": [i["probability"] for i in items if i.get("probability") is not None],
    }
    # Sweep the interpolated normalization (the score-semantics comparison
    # decides the SWAP-1 parsing); the .probability (top-level certainty)
    # reading is reported in score_semantics and swept only as a fallback.
    interp_confs = []
    for item in items:
        if item.get("score_raw"):
            interp = _score_interpolated(item["score_raw"])
            if interp is not None:
                interp_confs.append(interp)
    if interp_confs:
        signals["score_interpolated"] = interp_confs
    elif any(i.get("score_probability") is not None for i in items):
        signals["score"] = [
            float(i["score_probability"])
            for i in items
            if i.get("score_probability") is not None
        ]
    jev_cost = report.get("cost_usd_per_call_mean") or JEV_COST_PER_CALL_DEFAULT
    sweeps = {
        signal: tau_sweep_table(confs, jev_cost, LLM_COST_PER_CALL)
        for signal, confs in signals.items()
        if confs
    }
    if sweeps:
        report["tau_sweep"] = {
            "tau_values": TAU_VALUES,
            "llm_cost_per_call": LLM_COST_PER_CALL,
            "jev_cost_per_call": round(jev_cost, 6),
            "note": (
                "agreement = items with Jev confidence >= tau (all-pass golden "
                "set); cost ratio = cascade/llm-only with real LLM cost only on "
                "escalated items."
            ),
            "signals": sweeps,
        }
    return report


def _print_sweep(report: dict) -> None:
    sweep = report.get("tau_sweep")
    if not sweep:
        print("No tau_sweep in report (no evaluated items).")
        return
    print(
        f"tau sweep (jev ${sweep['jev_cost_per_call']:.6f}/call, "
        f"llm ${sweep['llm_cost_per_call']:.4f}/call):"
    )
    for signal, rows in sweep["signals"].items():
        print(f"  signal: {signal}")
        print("  | tau  | escal% | agree% | cascade$ | llm-only$ | ratio |")
        for row in rows:
            print(
                f"  | {row['tau']:.2f} | {row['escalation_rate'] * 100:5.1f} | "
                f"{row['agreement_rate'] * 100:5.1f} | "
                f"{row['cascade_est_cost_usd']:.6f} | "
                f"{row['llm_only_est_cost_usd']:.6f} | "
                f"{row['cost_ratio_cascade_vs_llm']:.3f} |"
            )
    semantics = report.get("score_semantics")
    if semantics:
        print("score-semantics comparison:")
        for key in ("top_level_certainty_probability", "interpolated_score_normalized"):
            stats = semantics[key]
            print(
                f"  {key}: mean={stats['mean_conf']} min={stats['min_conf']} "
                f"acc@0.5={stats['accuracy_at_0.5']} ece={stats['ece_10bin']}"
            )


def run() -> int:
    provider = get_decision_provider()
    if provider is None:
        print(
            "Decision provider unavailable. Run with the Jev kill switch on "
            "and a key in the environment:\n"
            "    cd backend\n"
            "    set -a; source ../.env; set +a\n"
            "    RAG_DECISION_PROVIDER=jev ../.venv/bin/python "
            "tests/eval/decision_calibration.py"
        )
        return 1

    items = json.loads(GOLDEN_SET_PATH.read_text())["queries"]
    results: list[dict] = []
    skipped_no_verdict = 0
    skipped_unknown_verdict = 0
    skipped_errors = 0
    cost_usd_total = 0.0

    for item in items:
        label = verdict_to_label(item.get("human_verdict"))
        if label is None:
            if item.get("human_verdict") is None:
                skipped_no_verdict += 1
            else:
                skipped_unknown_verdict += 1
            results.append(
                {"id": item.get("id"), "verdict": item.get("human_verdict"),
                 "probability": None, "label": None, "skipped": "no_verdict"}
            )
            continue
        try:
            answers = provider.decide(
                _state_for(item["query"], item.get("reference_answer", "")),
                {QUESTION_NAME: QUESTION, SCORE_QUESTION_NAME: SCORE_QUESTION},
            )
        except Exception as exc:  # skip + count; calibration must not abort
            skipped_errors += 1
            print(f"  skip id={item.get('id')}: decision call failed ({exc})")
            results.append(
                {"id": item.get("id"), "verdict": item.get("human_verdict"),
                 "probability": None, "label": label, "skipped": "error"}
            )
            continue
        answer = answers.get(QUESTION_NAME)
        score_answer = answers.get(SCORE_QUESTION_NAME)
        if answer is None and score_answer is None:
            skipped_errors += 1
            results.append(
                {"id": item.get("id"), "verdict": item.get("human_verdict"),
                 "probability": None, "label": label, "skipped": "missing_answer"}
            )
            continue
        cost = None
        for a in (answer, score_answer):
            if a is not None and a.cost_usd is not None:
                cost = a.cost_usd  # call-level cost, shared by both questions
                break
        if cost is not None:
            cost_usd_total += cost
        results.append(
            {
                "id": item.get("id"),
                "verdict": item.get("human_verdict"),
                "probability": round(answer.probability, 4) if answer else None,
                "raw": answer.raw if answer else None,
                "score_probability": (
                    round(score_answer.probability, 4) if score_answer else None
                ),
                "score_raw": score_answer.raw if score_answer else None,
                "cost_usd": round(cost, 6) if cost is not None else None,
                "label": label,
                "skipped": None,
            }
        )

    evaluated = [r for r in results if r["probability"] is not None]
    probabilities = [r["probability"] for r in evaluated]
    labels = [r["label"] for r in evaluated]

    tp = sum(1 for p, y in zip(probabilities, labels) if p >= POSITIVE_THRESHOLD and y == 1)
    fp = sum(1 for p, y in zip(probabilities, labels) if p >= POSITIVE_THRESHOLD and y == 0)
    tn = sum(1 for p, y in zip(probabilities, labels) if p < POSITIVE_THRESHOLD and y == 0)
    fn = sum(1 for p, y in zip(probabilities, labels) if p < POSITIVE_THRESHOLD and y == 1)
    total = len(probabilities)
    accuracy = (tp + tn) / total if total else None
    precision = tp / (tp + fp) if (tp + fp) else None
    recall = tp / (tp + fn) if (tp + fn) else None
    ece, bins = (
        expected_calibration_error(probabilities, labels) if total else (None, [])
    )

    verdict_distribution: dict[str, int] = {}
    for item in items:
        key = str(item.get("human_verdict"))
        verdict_distribution[key] = verdict_distribution.get(key, 0) + 1

    n_calls = len(evaluated)
    report = {
        "model": "typesafe/jev via System One noul+score",
        "question": QUESTION.instructions,
        "score_question": SCORE_QUESTION.instructions,
        "score_criteria": CONFIDENCE_LEVELS,
        "positive_threshold": POSITIVE_THRESHOLD,
        "ece_bins_requested": ECE_BINS,
        "total_items": len(items),
        "evaluated": n_calls,
        "skipped_no_verdict": skipped_no_verdict,
        "skipped_unknown_verdict": skipped_unknown_verdict,
        "skipped_errors": skipped_errors,
        "verdict_distribution": verdict_distribution,
        "note": (
            "Golden set currently holds only 'pass' positives + unreviewed "
            "nulls; FP/TN are structurally zero, accuracy equals recall and "
            "precision is undefined until negative verdicts exist."
            if tp > 0 and fp == 0 and tn == 0
            else None
        ),
        "confusion_matrix": {"tp": tp, "fp": fp, "tn": tn, "fn": fn},
        "accuracy": round(accuracy, 4) if accuracy is not None else None,
        "precision": round(precision, 4) if precision is not None else None,
        "recall": round(recall, 4) if recall is not None else None,
        "ece_10bin": round(ece, 4) if ece is not None else None,
        "ece_bins": bins,
        "cost_usd_total": round(cost_usd_total, 6),
        "cost_usd_per_call_mean": (
            round(cost_usd_total / n_calls, 6) if n_calls else None
        ),
        "items": results,
    }

    report = _append_offline_analytics(report)
    REPORT_PATH.write_text(json.dumps(report, indent=2))
    print(f"\nGolden set items: {len(items)} (evaluated {n_calls}, "
          f"skipped no-verdict {skipped_no_verdict}, "
          f"unknown {skipped_unknown_verdict}, errors {skipped_errors})")
    print(f"Verdict distribution: {verdict_distribution}")
    print(f"Confusion matrix @ {POSITIVE_THRESHOLD}: TP={tp} FP={fp} TN={tn} FN={fn}")
    print(f"Accuracy: {accuracy and round(accuracy, 4)}  "
          f"Precision: {precision and round(precision, 4)}  "
          f"Recall: {recall and round(recall, 4)}")
    print(f"ECE ({ECE_BINS} bins): {ece and round(ece, 4)}")
    print(f"Cost: ${cost_usd_total:.6f} total "
          f"(${cost_usd_total / n_calls:.6f}/call)" if n_calls else "Cost: $0")
    _print_sweep(report)
    print(f"Report written to {REPORT_PATH}")
    return 0 if n_calls else 1


def sweep() -> int:
    """Offline re-analysis of the stored report: tau sweep + score semantics."""
    if not REPORT_PATH.exists():
        print(f"Report not found: {REPORT_PATH}. Run the live calibration first.")
        return 1
    report = json.loads(REPORT_PATH.read_text())
    report = _append_offline_analytics(report)
    REPORT_PATH.write_text(json.dumps(report, indent=2))
    _print_sweep(report)
    print(f"Updated {REPORT_PATH} (offline, zero API spend)")
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--sweep",
        action="store_true",
        help="offline tau sweep + score semantics from the stored report "
        "(no API spend; requires a prior live calibration run)",
    )
    args = parser.parse_args(argv)
    return sweep() if args.sweep else run()


if __name__ == "__main__":
    sys.exit(main())
