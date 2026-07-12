"""MCP tool registration smoke (no FastMCP required for import of register_tools)."""

from __future__ import annotations

import pytest


class _FakeMCP:
    def __init__(self) -> None:
        self.tools: dict[str, object] = {}

    def tool(self):
        def deco(fn):
            self.tools[fn.__name__] = fn
            return fn

        return deco


@pytest.mark.unit
@pytest.mark.certification
def test_mcp_registers_required_tools() -> None:
    from brokers.mcp.tools import register_tools

    mcp = _FakeMCP()
    register_tools(mcp)
    required = {
        "broker_connect",
        "broker_quote",
        "broker_history",
        "broker_subscribe",
        "broker_positions",
        "broker_orders",
        "broker_place_order",
        "broker_modify_order",
        "broker_cancel_order",
        "broker_option_chain",
        "broker_market_depth",
        "broker_health",
        "broker_capabilities",
        "broker_symbol_lookup",
        "broker_instrument_lookup",
        "broker_verify",
        "broker_doctor",
    }
    missing = required - set(mcp.tools)
    assert not missing, f"missing MCP tools: {missing}"


@pytest.mark.unit
@pytest.mark.certification
def test_mcp_quote_tool_paper() -> None:
    from brokers.mcp.tools import register_tools

    mcp = _FakeMCP()
    register_tools(mcp)
    out = mcp.tools["broker_quote"](symbol="RELIANCE", broker="paper")
    assert out["symbol"] == "RELIANCE"
    assert out["quote"] is not None
