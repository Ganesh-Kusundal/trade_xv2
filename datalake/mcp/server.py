"""MCP server setup — FastMCP-based server for datalake capabilities."""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

try:
    from mcp.server.fastmcp import FastMCP

    mcp = FastMCP("datalake")
    HAS_MCP = True
except ImportError:
    HAS_MCP = False
    mcp = None
    logger.warning("mcp package not installed. Run: pip install mcp")


def create_server() -> Any:
    """Create and configure the MCP server with all tools and resources."""
    if not HAS_MCP:
        raise ImportError("mcp package required. Install with: pip install mcp")

    from datalake.mcp.resources import register_resources
    from datalake.mcp.tools import register_tools

    register_tools(mcp)
    register_resources(mcp)

    return mcp


def run_server(transport: str = "stdio") -> None:
    """Run the MCP server."""
    server = create_server()
    server.run(transport=transport)
