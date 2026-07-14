"""Datalake MCP server lifecycle — builds the FastMCP instance and runs it.

Read-only analysis only: every registered tool is a bound method of
:class:`DatalakeTools` (see ``tools.py``), which never writes to the
datalake or touches a broker/gateway.
"""

from __future__ import annotations

import logging

from mcp.server.fastmcp import FastMCP

from datalake.mcp.tools import DEFAULT_ROOT, DatalakeTools

logger = logging.getLogger(__name__)


def create_server(root: str = DEFAULT_ROOT) -> FastMCP:
    """Build a FastMCP instance with every datalake analysis tool registered."""
    mcp = FastMCP(
        name="datalake",
        instructions=(
            "Read-only analysis tools over the local NSE candle datalake "
            f"at {root!r}: historical OHLCV, sync/catalog status, gap and "
            "corruption checks, and a guarded freeform SQL query tool. "
            "No tool can write to the datalake or place/query live orders."
        ),
    )
    tools = DatalakeTools(root=root)
    for fn in (
        tools.history,
        tools.latest,
        tools.list_symbols,
        tools.symbol_status,
        tools.catalog_summary,
        tools.quality_check,
        tools.health_check,
        tools.query,
    ):
        mcp.add_tool(fn, name=fn.__name__)
    return mcp


def run_server() -> None:
    """Entry point for the ``datalake-mcp`` console script (stdio transport)."""
    create_server().run(transport="stdio")


if __name__ == "__main__":
    run_server()
