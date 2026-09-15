"""Finish coverage for backend/src/mcp/tools/knowledge.py.

Existing test_mcp_tools.py covers unknown class + unavailable store.
The single missing line is the success path of get_rag_collection_stats.
Loaded via spec with a stubbed retriever so no chromadb is required.
"""

from __future__ import annotations

import importlib.util
import sys
import types
from unittest.mock import MagicMock

# Stub backend.src.rag.retriever before loading knowledge.py so the test
# runs without chromadb (CI has it; local env does not).
_stub_retriever_mod = types.ModuleType("backend.src.rag.retriever")
_stub_retriever_mod.get_retriever = lambda: None  # placeholder, patched per-test
sys.modules.setdefault("backend.src.rag.retriever", _stub_retriever_mod)
# Ensure parent packages exist as namespaces for the stub.
for _name in ("backend.src.rag",):
    if _name not in sys.modules:
        _pkg = types.ModuleType(_name)
        _pkg.__path__ = []  # type: ignore[attr-defined]
        sys.modules[_name] = _pkg

import pathlib as _pl  # noqa: E402

_REPO = _pl.Path(__file__).resolve().parents[3]
_SPEC = importlib.util.spec_from_file_location(
    "mcp_knowledge_under_test",
    str(_REPO / "backend" / "src" / "mcp" / "tools" / "knowledge.py"),
)
assert _SPEC and _SPEC.loader
_mod = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_mod)


class TestAnomalyClassInfo:
    def test_all_classes_known(self):
        for cls in ["A1", "A2", "A3", "A4", "A5", "A6", "A7"]:
            out = _mod.get_anomaly_class_info(cls)
            assert out["anomaly_class"] == cls
            assert out["name"]
            assert out["recommended_action"]

    def test_case_insensitive(self):
        assert _mod.get_anomaly_class_info("a1")["anomaly_class"] == "A1"

    def test_unknown(self):
        out = _mod.get_anomaly_class_info("A9")
        assert "unknown anomaly class" in out["error"]

    def test_empty_string(self):
        out = _mod.get_anomaly_class_info("")
        assert "unknown anomaly class" in out["error"]


class TestCollectionStats:
    def test_unavailable(self, monkeypatch):
        monkeypatch.setattr(_mod, "get_retriever", lambda: None)
        assert _mod.get_rag_collection_stats() == {"error": "vector store unavailable"}

    def test_success_passthrough(self, monkeypatch):
        fake = MagicMock()
        fake.get_collection_stats.return_value = {"total_chunks": 42, "collection_name": "laad"}
        monkeypatch.setattr(_mod, "get_retriever", lambda: fake)
        out = _mod.get_rag_collection_stats()
        assert out == {"total_chunks": 42, "collection_name": "laad"}
        fake.get_collection_stats.assert_called_once_with()
