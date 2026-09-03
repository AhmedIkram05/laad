"""LAAD MCP server: exposes RAG + structured data tools to agents via Streamable HTTP/stdio.

Run standalone:  python -m backend.src.mcp.server --transport http
"""

from __future__ import annotations

import argparse

from mcp.server.fastmcp import FastMCP

from backend.src.mcp.tools import ALL_TOOLS

mcp = FastMCP("laad", host="0.0.0.0", port=8001)

for _tool in ALL_TOOLS:
    mcp.add_tool(_tool)


def main() -> None:
    parser = argparse.ArgumentParser(description="LAAD MCP server")
    parser.add_argument("--transport", choices=["http", "stdio"], default="http")
    args = parser.parse_args()
    mcp.run(transport="streamable-http" if args.transport == "http" else "stdio")


if __name__ == "__main__":
    main()
