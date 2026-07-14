"""Read-only MCP server exposing the datalake for LLM-driven analysis."""

from datalake.mcp.server import create_server, run_server

__all__ = ["create_server", "run_server"]
