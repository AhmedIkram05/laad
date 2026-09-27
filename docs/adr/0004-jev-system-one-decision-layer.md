# 0004 — Adopt TypeSafe Jev (System One) as the typed decision layer for RAG

**Status**: Accepted (2026-09-27) · [Reports](../../backend/tests/eval/decision_calibration_report.json) · [Benchmark](../../backend/tests/eval/decision_benchmark_report.json)

RAG's judgment calls — how confident is this answer, is it sound enough to skip critique, are the citations grounded, what kind of question is this — were shoehorned through the text-generation API: the LLM was asked in prose to rate its own confidence, then the free-text reply was regex-parsed. That path is expensive (a full LLM call per judgment, on top of generation), poorly calibrated (the LLM's verbalized confidence is nearly always high, and its self-rating on the golden set agreed with the ≥ 0.5 bar only 4.9% of the time at ECE 0.951), and structurally awkward — a judgment is a typed answer, not a chat completion.

We adopt the JevDecisionClient (`backend/src/rag/decision_client.py`) as a typed decision provider **beside** the LLM client, not instead of it: a `DecisionClient` protocol returning `DecisionAnswer(name, probability, confidence, cost_usd, raw)` per named `DecisionQuestion` (noul / score / choice). Three swaps land on the generation path — score-typed verbalized confidence with interpolated legend semantics, a noul sound-gate before Reflexion critique, and an optional noul citation verifier — plus a Jev Choice intent router for the hybrid planner whose option set mirrors the deterministic keyword classifier's vocabulary exactly. Every consumer keeps its existing path as the fallback: provider off (`RAG_DECISION_PROVIDER=heuristic`, the kill switch default) is byte-identical to pre-Jev behavior, and any decision failure (circuit open, timeout, missing answer), below-threshold confidence, or unknown choice option degrades gracefully into that same path — decision calls never raise into the graph. The score swap escalates to the LLM path below `RAG_JEV_ESCALATION_THRESHOLD` (cascade), and the escalation count is surfaced on the query's `rag.query` span (`decision.escalations`) alongside per-call `decision.jev` spans.

## Considered options

- **LLM-only status quo**: rejected — measured 4.9% agreement at $0.0164 per 41-item sweep vs Jev-only's 82.9% at $0.000891 (18× cheaper), and text-parsed confidence is the calibration problem this ADR exists to fix.
- **Heuristics only**: rejected as the sole path — the deterministic keyword classifier is free and instant, which is exactly why it stays as the intent-routing fallback, but heuristics cannot judge answer soundness or confidence against retrieved context.
- **LLM + Jev cascade (chosen)**: Jev answers first (~$0.000016/call); low-confidence items escalate to the existing LLM path, so worst case costs LLM-only plus one Jev call, while well-calibrated Jev answers short-circuit the expensive call.

## Consequences

- Measured on the 41-item golden-set benchmark (offline, all arms over the same items): Jev-only 82.9% agreement at $0.000891 (ECE 0.397), LLM-only 4.9% at $0.0164 (ECE 0.951), cascade at τ=0.55 68.3% at $0.006491 (ECE 0.537, 34.2% escalation rate, ~40% of LLM-only cost). Interpolated score semantics beat top-level certainty on the calibration report (ECE 0.397 vs 0.737).
- Known limitation: the golden set has zero negative verdicts, so the false-pass rate is unmeasurable — the benchmark certifies agreement, not discrimination.
- The full RAGAS 3-arm parity matrix is pending the docker baseline run; the offline benchmark is the current evidence base.
- Per-question cost attribution is unavailable: the System One response reports one usage cost per call, shared across the questions in it.
- `RAG_JEV_ESCALATION_THRESHOLD`'s code default stays 0.7; 0.55 is the empirically recommended environment setting from the τ sweep and is documented in the README, not changed in code.
- Kill-switch discipline: `RAG_DECISION_PROVIDER=heuristic` must remain byte-identical; eval cache signatures key on the decision-provider env (`run_ragas.py` `_CACHE_SIGNATURE_KEYS`) so a cached run can never silently mix providers.
