"""Adapter: expose the LAAD MCP server's tools to LangChain/LangGraph.

Transport resolution:
  - MCP_SERVER_URL set (compose prod): connect over the wire via streamable_http_client.
  - MCP_SERVER_URL unset/empty (tests, local dev): in-process connection
    through mcp.shared.memory — same ClientSession API, no network.

Both paths return langchain tools bound to a long-lived ClientSession.
"""

from __future__ import annotations

import os

from langchain_mcp_adapters.tools import convert_mcp_tool_to_langchain_tool
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from mcp.shared.memory import create_connected_server_and_client_session

from backend.src.mcp.server import mcp as _mcp

# (session, tools, context_manager) — the CM must stay referenced or GC
# finalizes it and cancels the in-process server task mid-call.
_shared: tuple[ClientSession, list, object] | None = None


async def get_langchain_tools() -> list:
    """Return the LAAD MCP tools as LangChain tools (cached singleton)."""
    global _shared
    if _shared is not None:
        return _shared[1]
    url = os.getenv("MCP_SERVER_URL", "")
    if url:
        cm = streamable_http_client(url)
        read, write, _ = await cm.__aenter__()
        session = await ClientSession(read, write).__aenter__()
    else:
        cm = create_connected_server_and_client_session(_mcp._mcp_server)
        session = await cm.__aenter__()
    result = await session.list_tools()
    tools = [convert_mcp_tool_to_langchain_tool(session, t) for t in result.tools]
    _shared = (session, tools, cm)
    return tools


def reset_tools() -> None:
    """Drop the cached singleton (tests only)."""
    global _shared
    _shared = None
