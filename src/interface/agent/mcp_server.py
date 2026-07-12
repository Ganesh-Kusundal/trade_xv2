"""Optional MCP server exposing AgentTools.

This module is *import-safe without the optional ``mcp`` dependency*: the
import is guarded so that ``import interface.agent.mcp_server`` never fails on
a machine that only installed the base package. The MCP server itself is only
built when ``mcp`` is present (the ``agent`` extra).

The server is a thin translation layer: each MCP tool call is forwarded to
``dispatch_tool``, so the exact same ``AgentTools`` + ``AgentGuardrails`` path
an in-process loop uses is reused — no second code path, no bypassed guards.
"""

from __future__ import annotations

from typing import Any

try:
    from mcp import types as mcp_types
    from mcp.server import Server

    _MCP_AVAILABLE = True
except Exception:  # pragma: no cover - depends on optional dep
    mcp_types = None  # type: ignore[assignment]
    Server = None  # type: ignore[assignment]
    _MCP_AVAILABLE = False

from interface.agent.tools import AgentTools
from interface.agent.tools_schema import AGENT_TOOL_SPECS, dispatch_tool


def mcp_available() -> bool:
    return _MCP_AVAILABLE


def _specs_as_mcp_tools() -> list[Any]:
    """Convert the Anthropic tool specs into MCP Tool definitions."""
    tools = []
    for spec in AGENT_TOOL_SPECS:
        tools.append(
            mcp_types.Tool(
                name=spec["name"],
                description=spec.get("description", ""),
                inputSchema=spec["input_schema"],
            )
        )
    return tools


def build_server(tools: AgentTools, name: str = "tradex-agent") -> Any:
    """Build (but do not run) an MCP server wrapping the given AgentTools.

    Raises RuntimeError if the ``mcp`` package is not installed.
    """
    if not _MCP_AVAILABLE:
        raise RuntimeError(
            "The 'mcp' package is required for the agent MCP server. "
            "Install the 'agent' extra: pip install -e '.[agent]'"
        )

    app = Server(name)

    @app.list_tools()
    async def list_tools() -> list[Any]:  # type: ignore[no-untyped-def]
        return _specs_as_mcp_tools()

    @app.call_tool()
    async def call_tool(name: str, arguments: dict[str, Any]) -> list[Any]:  # type: ignore[no-untyped-def]
        try:
            result = dispatch_tool(tools, name, arguments or {})
            payload = str(result)
            is_error = False
        except Exception as exc:
            payload = f"tool error: {exc}"
            is_error = True
        return [mcp_types.TextContent(type="text", text=payload, is_error=is_error)]

    return app


def run_stdio(tools: AgentTools, name: str = "tradex-agent") -> None:
    """Run the agent MCP server over stdio (blocking). Requires ``mcp``."""
    import anyio  # type: ignore[import-not-found]  # pragma: no cover

    app = build_server(tools, name)

    async def _main() -> None:  # pragma: no cover - exercised only at runtime
        from mcp.server.stdio import stdio_server

        async with stdio_server() as (read, write):
            await app.run(read, write, app.create_initialization_options())

    anyio.run(_main)


__all__ = ["build_server", "mcp_available", "run_stdio"]
