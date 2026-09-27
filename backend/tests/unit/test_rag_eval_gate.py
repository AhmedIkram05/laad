"""Tests for the run_ragas eval gate's provider-key neutral mode.

With no LLM provider key the gate must stay loud: exit 0, a ::warning::
annotation, and (under --ci) a {"skipped": true, "reason": ...} marker in
results.json instead of a silent green pass.
"""

from __future__ import annotations

import json
import os
from unittest.mock import patch

import pytest

pytestmark = pytest.mark.rag


@pytest.fixture(scope="module", autouse=True)
def _stop_ragas_analytics_flusher():
    """Importing run_ragas imports ragas, whose _analytics module starts a
    daemon thread doing `time.sleep(1)` in a loop at import time (module-level
    AnalyticsBatcher singleton, not gated by RAGAS_DO_NOT_TRACK). Left running,
    it hijacks any later test that patches the process-global time.sleep —
    e.g. the write-helper backoff tests in CI. Stop it at module teardown."""
    yield
    try:
        from ragas import _analytics

        _analytics._analytics_batcher._running = False
    except Exception:  # pragma: no cover - ragas not installed / API drift
        pass

_KEY_VARS = ("WANDB_API_KEY", "LLM_API_KEY", "OPENROUTER_API_KEY", "TYPESAFE_API_KEY")


def _blank_keys():
    return patch.dict(os.environ, {k: "" for k in _KEY_VARS}, clear=False)


class TestHasProviderKey:
    def test_true_when_wandb_key_set(self):
        from backend.tests.eval.run_ragas import _has_provider_key

        with patch.dict(os.environ, {"WANDB_API_KEY": "x"}, clear=False):
            assert _has_provider_key() is True

    def test_true_when_openrouter_key_set(self):
        from backend.tests.eval.run_ragas import _has_provider_key

        with patch.dict(os.environ, {"OPENROUTER_API_KEY": "x"}, clear=False):
            assert _has_provider_key() is True

    def test_true_when_typesafe_key_set(self):
        from backend.tests.eval.run_ragas import _has_provider_key

        with patch.dict(os.environ, {"TYPESAFE_API_KEY": "x"}, clear=False):
            assert _has_provider_key() is True

    def test_false_when_all_blank(self):
        from backend.tests.eval.run_ragas import _has_provider_key

        with _blank_keys():
            assert _has_provider_key() is False


class TestGateSkip:
    def test_main_ci_skips_with_annotation_and_marker(self, tmp_path, capsys):
        from backend.tests.eval import run_ragas

        out = tmp_path / "results.json"
        with _blank_keys():
            rc = run_ragas.main(
                [
                    "--ci",
                    "--out",
                    str(out),
                    "--baseline",
                    str(tmp_path / "absent.json"),
                ]
            )

        captured = capsys.readouterr().out
        assert rc == 0
        assert "::warning::" in captured
        assert json.loads(out.read_text()) == {
            "skipped": True,
            "reason": "no provider key",
        }

    def test_main_local_skip_is_loud_but_exit_0(self, tmp_path, capsys):
        from backend.tests.eval import run_ragas

        out = tmp_path / "results.json"
        with _blank_keys():
            rc = run_ragas.main(["--out", str(out)])

        assert rc == 0
        assert "::warning::" in capsys.readouterr().out
        assert not out.exists()

    def test_skip_never_reaches_seed(self, tmp_path, capsys):
        """No provider key -> main returns before seeding DB/chroma."""
        from backend.tests.eval import run_ragas

        with _blank_keys(), patch.object(run_ragas, "seed") as seed_mock:
            rc = run_ragas.main(["--out", str(tmp_path / "results.json")])

        assert rc == 0
        seed_mock.assert_not_called()
        assert "::warning::" in capsys.readouterr().out
