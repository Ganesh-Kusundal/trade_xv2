#!/usr/bin/env python3
"""MCP integration test — STUBBED (SM-13).

No MCP servers exist in src/ as of Phase 4a.  The old test imported
``datalake.mcp.server`` which was never implemented.  This stub documents
the gap and exits cleanly so CI does not fail on a missing import.
"""

import sys


def main() -> None:
    print("=" * 60)
    print("TradeXV2 MCP Integration Test — SKIPPED (SM-13)")
    print("=" * 60)
    print()
    print("No MCP servers exist in src/.  See docs/architecture/AUDIT-current-state.md")
    print("and the Phase 4a plan (SM-13) for context.")
    print()
    print("If MCP servers are added in the future, restore this test against the")
    print("concrete server module and re-enable the entry-point in pyproject.toml.")
    print()
    print("SKIPPED")


if __name__ == "__main__":
    main()
