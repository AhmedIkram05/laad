"""MCP server + tools + LangChain adapter tests.

Runs in-process against the FastMCP server (no wire transport needed).
Requires postgres_test (seeded via init_db) and chromadb for the SQL/vector tools.
"""

from __future__ import annotations

import asyncio
import json

import pytest

pytestmark = [pytest.mark.rag, pytest.mark.chroma]

from mcp.shared.memory import create_connected_server_and_client_session  # noqa: E402

from backend.src.mcp.server import mcp  # noqa: E402

EXPECTED_TOOLS = {
    "search_knowledge",
    "query_anomalies",
    "get_anomaly",
    "get_machine_history",
    "get_atm_metrics",
    "get_statistics",
    "search_events",
    "get_error_context",
    "get_atm_info",
    "compare_atms",
    "get_anomaly_class_info",
    "get_rag_collection_stats",
}


def _run(coro):
    return asyncio.run(coro)


async def _call_tool(session, name, args):
    result = await session.call_tool(name, args)
    text = result.content[0].text
    return json.loads(text) if text else {}


class TestToolRegistry:
    def test_tools_listed(self):
        async def _go():
            async with create_connected_server_and_client_session(
                mcp._mcp_server
            ) as session:
                res = await session.list_tools()
                return {t.name for t in res.tools}

        names = _run(_go())
        assert names == EXPECTED_TOOLS


class TestSearchKnowledge:
    def test_search_knowledge_shape(self, monkeypatch):
        from backend.src.rag.retriever import RetrievedChunk

        class _FakeRetriever:
            collection = object()

            def retrieve(
                self,
                query,
                atm_id=None,
                top_k=None,
                anomaly_type=None,
                temporal_boost=True,
                error_only=None,
                most_recent_first=None,
            ):
                return [
                    RetrievedChunk(
                        text="2026-05-15T10:00:00Z [ATM_APP] NETWORK_DISCONNECT: ATM-GB-0001 connection lost",
                        chunk_id="chunk-1",
                        atm_id="ATM-GB-0001",
                        timestamp="2026-05-15T10:00:00Z",
                        distance=0.1,
                        confidence_score=0.9,
                    )
                ]

        monkeypatch.setattr(
            "backend.src.mcp.tools.vector.get_retriever", lambda: _FakeRetriever()
        )

        async def _go():
            async with create_connected_server_and_client_session(
                mcp._mcp_server
            ) as session:
                return await _call_tool(
                    session,
                    "search_knowledge",
                    {
                        "query": "network disconnect",
                        "atm_id": "ATM-GB-0001",
                    },
                )

        out = _run(_go())
        assert out["count"] == 1
        chunk = out["chunks"][0]
        assert chunk["chunk_id"] == "chunk-1"
        assert chunk["atm_id"] == "ATM-GB-0001"
        assert chunk["confidence_score"] == 0.9
        assert "NETWORK_DISCONNECT" in chunk["text"]

    def test_search_knowledge_store_unavailable(self, monkeypatch):
        monkeypatch.setattr("backend.src.mcp.tools.vector.get_retriever", lambda: None)

        async def _go():
            async with create_connected_server_and_client_session(
                mcp._mcp_server
            ) as session:
                return await _call_tool(
                    session, "search_knowledge", {"query": "anything"}
                )

        out = _run(_go())
        assert out["error"] == "vector store unavailable"
        assert out["chunks"] == []
        assert out["count"] == 0


class TestSqlTools:
    def test_query_anomalies_empty_shape(self):
        async def _go():
            async with create_connected_server_and_client_session(
                mcp._mcp_server
            ) as session:
                return await _call_tool(
                    session, "query_anomalies", {"atm_id": "ATM-GB-0001"}
                )

        out = _run(_go())
        assert out["count"] == 0
        assert out["rows"] == []

    def test_get_atm_info_seeded(self):
        async def _go():
            async with create_connected_server_and_client_session(
                mcp._mcp_server
            ) as session:
                return await _call_tool(
                    session, "get_atm_info", {"atm_id": "ATM-GB-0001"}
                )

        out = _run(_go())
        assert out["atm_id"] == "ATM-GB-0001"
        assert out["os_version"]
        assert out["location_code"]

    def test_get_atm_info_unknown(self):
        async def _go():
            async with create_connected_server_and_client_session(
                mcp._mcp_server
            ) as session:
                return await _call_tool(
                    session, "get_atm_info", {"atm_id": "ATM-NOPE-9999"}
                )

        out = _run(_go())
        assert "not found" in out["error"]

    def test_get_statistics_zero_shape(self):
        async def _go():
            async with create_connected_server_and_client_session(
                mcp._mcp_server
            ) as session:
                return await _call_tool(session, "get_statistics", {})

        out = _run(_go())
        assert set(out) == {"groups", "total", "active", "resolved"}
        assert out["total"] == 0
        assert out["active"] == 0
        assert out["resolved"] == 0

    def test_get_error_context_requires_one_id(self):
        async def _go():
            async with create_connected_server_and_client_session(
                mcp._mcp_server
            ) as session:
                return await _call_tool(session, "get_error_context", {})

        out = _run(_go())
        assert (
            "exactly one of correlation_id or transaction_id required" in out["error"]
        )

    def test_get_anomaly_missing(self):
        async def _go():
            async with create_connected_server_and_client_session(
                mcp._mcp_server
            ) as session:
                return await _call_tool(session, "get_anomaly", {"anomaly_id": 999999})

        out = _run(_go())
        assert "not found" in out["error"]

    def test_get_anomaly_class_info_known(self):
        async def _go():
            async with create_connected_server_and_client_session(
                mcp._mcp_server
            ) as session:
                return await _call_tool(
                    session, "get_anomaly_class_info", {"anomaly_class": "a3"}
                )

        out = _run(_go())
        assert out["anomaly_class"] == "A3"
        assert out["name"]
        assert out["recommended_action"]

    def test_get_anomaly_class_info_unknown(self):
        async def _go():
            async with create_connected_server_and_client_session(
                mcp._mcp_server
            ) as session:
                return await _call_tool(
                    session, "get_anomaly_class_info", {"anomaly_class": "A9"}
                )

        out = _run(_go())
        assert "unknown anomaly class" in out["error"]

    def test_get_rag_collection_stats_unavailable(self, monkeypatch):
        monkeypatch.setattr(
            "backend.src.mcp.tools.knowledge.get_retriever", lambda: None
        )

        async def _go():
            async with create_connected_server_and_client_session(
                mcp._mcp_server
            ) as session:
                return await _call_tool(session, "get_rag_collection_stats", {})

        out = _run(_go())
        assert out["error"] == "vector store unavailable"


class TestAdapter:
    def test_get_langchain_tools_in_process(self, monkeypatch):
        monkeypatch.setenv("MCP_SERVER_URL", "")
        from backend.src.mcp import adapter

        adapter.reset_tools()

        tools = _run(adapter.get_langchain_tools())
        assert len(tools) == 12
        names = {t.name for t in tools}
        assert names == EXPECTED_TOOLS
        assert all(getattr(t, "description", None) for t in tools)
        adapter.reset_tools()
