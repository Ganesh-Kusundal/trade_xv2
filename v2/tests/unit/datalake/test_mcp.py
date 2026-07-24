"""Minimal MCP tool list / call_tool interface — no network SDK."""

from __future__ import annotations

from pathlib import Path

from datalake.catalog import DataCatalog
from datalake.mcp_server import DatalakeMcpServer


def test_list_tools_includes_query_bars(tmp_path: Path) -> None:
    server = DatalakeMcpServer(DataCatalog(tmp_path))
    names = {t["name"] for t in server.list_tools()}
    assert "query_bars" in names


def test_call_tool_query_bars(tmp_path: Path) -> None:
    catalog = DataCatalog(tmp_path)
    catalog.write_bars(
        "RELIANCE",
        [
            {
                "timestamp": "2024-01-15T00:00:00+00:00",
                "open": 100,
                "high": 105,
                "low": 99,
                "close": 104,
                "volume": 1000,
            }
        ],
    )
    server = DatalakeMcpServer(catalog)
    result = server.call_tool(
        "query_bars",
        {
            "symbol": "RELIANCE",
            "start": "2024-01-01T00:00:00+00:00",
            "end": "2024-12-31T00:00:00+00:00",
        },
    )
    assert len(result) == 1
    assert result[0]["close"] == 104


def test_call_tool_unknown_raises(tmp_path: Path) -> None:
    server = DatalakeMcpServer(DataCatalog(tmp_path))
    try:
        server.call_tool("nope", {})
        assert False, "expected ValueError"
    except ValueError as exc:
        assert "nope" in str(exc)
