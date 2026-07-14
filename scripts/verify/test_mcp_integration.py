#!/usr/bin/env python3
"""MCP integration smoke test — datalake MCP server.

Confirms datalake.mcp.server builds a real FastMCP instance with every
expected read-only analysis tool registered, and that at least one tool
can be called end-to-end against the real datalake root. Restored now
that src/datalake/mcp/ exists (see scripts/verify/test_mcp_integration.py's
prior stub / SM-13 for the gap this fills, and the `datalake-mcp`
entry-point in pyproject.toml).

Usage:
    python scripts/verify/test_mcp_integration.py
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
SRC = ROOT / "src"
for p in (ROOT, SRC):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

EXPECTED_TOOLS = {
    "history",
    "latest",
    "list_symbols",
    "symbol_status",
    "catalog_summary",
    "quality_check",
    "health_check",
    "query",
}


async def _check_tools_registered() -> bool:
    from datalake.mcp.server import create_server

    server = create_server(root="data/lake")
    tools = await server.list_tools()
    names = {t.name for t in tools}
    missing = EXPECTED_TOOLS - names
    extra = names - EXPECTED_TOOLS
    if missing:
        print(f"  FAIL: missing tools: {sorted(missing)}")
        return False
    if extra:
        print(f"  NOTE: extra tools beyond the expected set: {sorted(extra)}")
    print(f"  OK: all {len(EXPECTED_TOOLS)} expected tools registered: {sorted(names)}")
    return True


def _check_list_symbols_callable() -> bool:
    from datalake.mcp.tools import DatalakeTools

    tools = DatalakeTools(root="data/lake")
    symbols = tools.list_symbols(timeframe="1m")
    if not isinstance(symbols, list):
        print(f"  FAIL: list_symbols() returned {type(symbols)}, expected list")
        return False
    print(f"  OK: list_symbols() returned {len(symbols)} symbols")
    return True


def main() -> int:
    print("=" * 60)
    print("TradeXV2 MCP Integration Test — datalake MCP server")
    print("=" * 60)

    print("\n[1/2] Building server and checking tool registration...")
    ok1 = asyncio.run(_check_tools_registered())

    print("\n[2/2] Calling list_symbols() against the real datalake root...")
    try:
        ok2 = _check_list_symbols_callable()
    except Exception as exc:
        print(f"  FAIL: {exc}")
        ok2 = False

    print()
    if ok1 and ok2:
        print("PASSED")
        return 0
    print("FAILED")
    return 1


if __name__ == "__main__":
    sys.exit(main())
