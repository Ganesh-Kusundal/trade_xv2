"""Minimal datalake MCP facade — list_tools / call_tool, no network SDK.

ponytail: in-process tool dispatch only; real MCP transport is a later package.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from datalake.catalog import DataCatalog


def _parse_ts(value: str | datetime) -> datetime:
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


class DatalakeMcpServer:
    """In-process tool list for query_bars against a DataCatalog."""

    def __init__(self, catalog: DataCatalog) -> None:
        self._catalog = catalog

    def list_tools(self) -> list[dict[str, str]]:
        return [
            {
                "name": "query_bars",
                "description": "Fetch OHLCV bars for symbol in [start, end]",
            },
            {
                "name": "sync_status",
                "description": "Check whether a symbol has local bars",
            },
        ]

    def call_tool(self, name: str, arguments: dict[str, Any]) -> Any:
        if name == "query_bars":
            return self._catalog.query_bars(
                symbol=str(arguments["symbol"]),
                start=_parse_ts(arguments["start"]),
                end=_parse_ts(arguments["end"]),
            )
        if name == "sync_status":
            symbol = str(arguments["symbol"])
            return {"symbol": symbol, "has_bars": self._catalog.has_bars(symbol)}
        raise ValueError(f"unknown tool: {name}")
