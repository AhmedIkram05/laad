"""LAAD MCP server: exposes RAG + structured data tools to agents via SSE/stdio.

Run standalone:  python -m backend.src.mcp.server --transport sse
"""
from __future__ import annotations

import argparse
import asyncio

from mcp.server.fastmcp import FastMCP

from backend.src.mcp.tools import ALL_TOOLS

mcp = FastMCP("laad", host="0.0.0.0", port=8001)

for _tool in ALL_TOOLS:
    mcp.add_tool(_tool)


def main() -> None:
    # host/port are constructor args on FastMCP (run_sse_async only takes mount_path).
    parser = argparse.ArgumentParser(description="LAAD MCP server")
    parser.add_argument("--transport", choices=["sse", "stdio"], default="sse")
    args = parser.parse_args()
    if args.transport == "sse":
        asyncio.run(mcp.run_sse_async())
    else:
        asyncio.run(mcp.run_stdio_async())


if __name__ == "__main__":
    main()