"""MCP server setup — FastMCP-based server for broker capabilities."""

from __future__ import annotations

import logging
from typing import Any

from brokers._bootstrap import ensure_repo_src

ensure_repo_src()

logger = logging.getLogger(__name__)

try:
    from mcp.server.fastmcp import FastMCP

    mcp = FastMCP("brokers")
    HAS_MCP = True
except ImportError:
    HAS_MCP = False
    mcp = None
    logger.warning("mcp package not installed. Run: pip install -e '.[mcp]'")


def create_server() -> Any:
    """Create and configure the brokers MCP server."""
    if not HAS_MCP:
        raise ImportError("mcp package required. Install with: pip install -e '.[mcp]'")

    from brokers.mcp.tools import register_tools

    register_tools(mcp)
    return mcp


def run_server(transport: str = "stdio") -> None:
    """Run the brokers MCP server."""
    server = create_server()
    server.run(transport=transport)


if __name__ == "__main__":
    run_server()
