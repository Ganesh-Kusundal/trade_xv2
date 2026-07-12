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

import logging
from typing import Any

logger = logging.getLogger(__name__)

try:
    from mcp.server.fastmcp import FastMCP

    _MCP_AVAILABLE = True
except Exception:  # pragma: no cover - depends on optional dep
    FastMCP = None  # type: ignore[assignment,misc]
    _MCP_AVAILABLE = False

from interface.agent.tools import AgentTools
from interface.agent.tools_schema import AGENT_TOOL_SPECS, dispatch_tool


def mcp_available() -> bool:
    return _MCP_AVAILABLE


def _build_arg_model(spec: dict[str, Any]) -> type:
    """Create a Pydantic ArgModelBase subclass from a JSON Schema input spec."""
    from pydantic import Field, create_model

    from mcp.server.fastmcp.utilities.func_metadata import ArgModelBase

    _TYPE_MAP: dict[str, type] = {
        "string": str,
        "integer": int,
        "number": float,
        "boolean": bool,
    }

    schema = spec.get("input_schema", {})
    props = schema.get("properties", {})
    required = set(schema.get("required", []))
    fields: dict[str, Any] = {}

    for name, prop in props.items():
        py_type = _TYPE_MAP.get(prop.get("type", "string"), str)
        desc = prop.get("description", "")
        if name in required:
            fields[name] = (py_type, Field(description=desc))
        else:
            default = prop.get("default")
            fields[name] = (py_type, Field(default=default, description=desc))

    model_name = f"{spec['name']}Args"
    return create_model(model_name, __base__=ArgModelBase, **fields)


def _make_handler(tools: AgentTools, tool_name: str) -> Any:
    """Return an async handler that dispatches to *tools* via *tool_name*."""

    async def handler(**kwargs: Any) -> str:
        result = dispatch_tool(tools, tool_name, kwargs)
        return str(result)

    handler.__name__ = tool_name
    return handler


def build_server(tools: AgentTools, name: str = "tradex-agent") -> Any:
    """Build (but do not run) a FastMCP server wrapping the given AgentTools.

    Raises RuntimeError if the ``mcp`` package is not installed.
    """
    if not _MCP_AVAILABLE:
        raise RuntimeError(
            "The 'mcp' package is required for the agent MCP server. "
            "Install the 'agent' extra: pip install -e '.[agent]'"
        )

    from mcp.server.fastmcp.tools import Tool
    from mcp.server.fastmcp.utilities.func_metadata import func_metadata

    server = FastMCP(name)

    for spec in AGENT_TOOL_SPECS:
        tool_name = spec["name"]
        description = spec.get("description", "")

        arg_model = _build_arg_model(spec)
        handler = _make_handler(tools, tool_name)
        fm = func_metadata(handler, skip_names=[])

        tool = Tool.from_function(
            handler,
            name=tool_name,
            description=description,
        )
        # Override auto-inferred schema with the declared AGENT_TOOL_SPECS schema.
        tool.parameters = spec.get("input_schema", {"type": "object", "properties": {}})
        tool.fn_metadata = fm
        tool.fn_metadata.arg_model = arg_model

        server._tool_manager._tools[tool_name] = tool

    return server


def run_stdio(tools: AgentTools, name: str = "tradex-agent") -> None:
    """Run the agent MCP server over stdio (blocking). Requires ``mcp``."""
    import anyio  # type: ignore[import-not-found]  # pragma: no cover

    server = build_server(tools, name)

    async def _main() -> None:  # pragma: no cover - exercised only at runtime
        await server.run_async(transport="stdio")

    anyio.run(_main)


__all__ = ["build_server", "mcp_available", "run_stdio"]
