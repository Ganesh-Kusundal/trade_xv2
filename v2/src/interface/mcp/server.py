"""MCP server facade — tool list (health included)."""

from __future__ import annotations

from typing import Any


def list_tools() -> list[dict[str, Any]]:
    return [
        {
            "name": "health",
            "description": "Liveness/readiness health check",
            "inputSchema": {"type": "object", "properties": {}},
        },
    ]


class MCPServer:
    def list_tools(self) -> list[dict[str, Any]]:
        return list_tools()
