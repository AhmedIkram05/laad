"""Agentic RAG smoke test — plan §7.5.

Three mini queries (1 semantic / 1 structured / 1 hybrid) through all three
systems, asserting dict-shaped outputs, non-empty answers and populated traces;
plus a ragas import + evaluate round-trip on one synthetic row.

Skipped when no LLM API key is configured. Pins the cheap config
(1 LLM call/query, D13 inert). CI runs host-side with `-m "not rag"` so this
file is deselected there entirely.

NOTE: this file's conftest session fixture truncates the shared atm_platform_test
DB — never run pytest suites while an eval (run_ragas) container is executing.
"""
import asyncio
import json
import os
import sys
import types

# Cheap config must be pinned BEFORE backend modules read the environment.
os.environ.setdefault("RAG_SAMPLES", "1")
os.environ.setdefault("RAG_REFLEXION", "false")
os.environ.setdefault("RAG_SELF_CONSISTENCY", "false")
os.environ.setdefault("RAG_CITATION_GROUNDING", "false")

import pytest  # noqa: E402

pytestmark = [pytest.mark.rag]

# ragas import shim: ChatVertexAI moved out of langchain-community in 0.4.x.
_stub = types.ModuleType("langchain_community.chat_models.vertexai")
_stub.ChatVertexAI = type("ChatVertexAI", (), {})
sys.modules.setdefault("langchain_community.chat_models.vertexai", _stub)

from backend.tests.eval.systems import (  # noqa: E402
    GOLDEN_SET_PATH,
    SystemResult,
    _ensure_patched,
    run_agent,
    run_baseline,
    seed,
)

GOLDEN = json.loads(GOLDEN_SET_PATH.read_text())["queries"]

MINI = [  # one semantic, one structured, one hybrid
    next(q for q in GOLDEN if q["category"] == "semantic"),
    next(q for q in GOLDEN if q["category"] == "structured"),
    next(q for q in GOLDEN if q["category"] == "hybrid"),
]

requires_llm = pytest.mark.skipif(
    not (os.getenv("LLM_API_KEY") or os.getenv("WANDB_API_KEY")),
    reason="no LLM API key configured (set LLM_API_KEY or WANDB_API_KEY)",
)


@pytest.fixture(scope="module", autouse=True)
def seeded_env():
    seed()  # idempotent: DB fixtures + chroma chunks; safe to re-run
    yield


@requires_llm
def test_three_systems_smoke():
    """Each mini query runs through all three systems with sane shapes."""
    from backend.src.rag.agent_types import AgentMode

    _ensure_patched()  # wire local tools (mcp-server unreachable in test stack)

    for q in MINI:
        baseline = run_baseline(q)
        assert isinstance(baseline, SystemResult)
        assert baseline.query == q["query"]
        assert baseline.answer, f"baseline empty answer for {q['id']}"

        for mode in (AgentMode.HYBRID, AgentMode.AGENTIC):
            result = asyncio.run(run_agent(q, mode))
            assert isinstance(result, SystemResult)
            assert result.query == q["query"]
            assert result.answer, f"{mode.value} empty answer for {q['id']}"
            assert result.agent_trace, f"{mode.value} missing trace for {q['id']}"
            assert result.agent_trace.get("tool_calls"), (
                f"{mode.value} ran no tools for {q['id']}"
            )
            assert result.agent_trace.get("selected_tools"), (
                f"{mode.value} missing selected_tools for {q['id']}"
            )


@requires_llm
def test_ragas_import_and_evaluate():
    """ragas imports cleanly and evaluates a single synthetic row."""
    from openai import OpenAI  # noqa: E402

    from backend.src.rag.config import config  # noqa: E402
    from ragas import evaluate  # noqa: E402
    from ragas.dataset_schema import EvaluationDataset  # noqa: E402
    from ragas.embeddings.base import LangchainEmbeddingsWrapper  # noqa: E402
    from ragas.llms.base import llm_factory  # noqa: E402
    from ragas.metrics import LLMContextRecall, LLMContextPrecisionWithReference  # noqa: E402
    from langchain_ollama import OllamaEmbeddings  # noqa: E402

    ds = EvaluationDataset.from_dict(
        [
            {
                "user_input": "smoke query",
                "reference": "a reference answer",
                "retrieved_contexts": ["context one", "context two"],
                "response": "a generated answer",
            }
        ]
    )
    judge = OpenAI(api_key=config.llm_api_key, base_url=config.llm_base_url)
    result = evaluate(
        ds,
        metrics=[LLMContextRecall(), LLMContextPrecisionWithReference()],
        llm=llm_factory(
            model=os.getenv("RAG_JUDGE_MODEL", "Qwen/Qwen3-30B-A3B-Instruct-2507"),
            provider="openai",
            client=judge,
        ),
        embeddings=LangchainEmbeddingsWrapper(
            OllamaEmbeddings(
                model="nomic-embed-text",
                base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"),
            )
        ),
    )
    assert result.scores, "ragas returned no per-sample scores"
    assert "context_recall" in result.scores[0]
    assert "llm_context_precision_with_reference" in result.scores[0]