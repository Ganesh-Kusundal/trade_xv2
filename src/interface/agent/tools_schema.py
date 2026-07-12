"""Anthropic tool schemas + dispatch for AgentTools.

Derives the JSON tool definitions (name / description / input_schema) the
agent loop hands to the LLM from the real ``AgentTools`` surface, and a
single dispatch entry point that routes a tool-call request to the matching
``AgentTools`` method.

The loop never calls broker code directly — every tool name resolves to an
existing ``AgentTools`` method (which already enforces ``AgentGuardrails``),
so guardrails cannot be bypassed by adding a new path here.
"""

from __future__ import annotations

from typing import Any

from interface.agent.tools import AgentTools

# Anthropic tool definitions. ``input_schema`` is a JSON Schema describing the
# arguments the LLM must supply. ``required`` omits arguments that have a
# default on the underlying method.
AGENT_TOOL_SPECS: list[dict[str, Any]] = [
    {
        "name": "get_quote",
        "description": "Fetch the latest quote (LTP, bid, ask, volume) for an equity.",
        "input_schema": {
            "type": "object",
            "properties": {
                "symbol": {"type": "string", "description": "Instrument symbol, e.g. RELIANCE."},
                "exchange": {"type": "string", "description": "Exchange, default NSE.", "default": "NSE"},
            },
            "required": ["symbol"],
        },
    },
    {
        "name": "get_history",
        "description": "Fetch historical candles for an equity over a timeframe/days window.",
        "input_schema": {
            "type": "object",
            "properties": {
                "symbol": {"type": "string"},
                "exchange": {"type": "string", "default": "NSE"},
                "timeframe": {"type": "string", "description": "e.g. 5m, 1D.", "default": "5m"},
                "days": {"type": "integer", "description": "Lookback window in days.", "default": 5},
            },
            "required": ["symbol"],
        },
    },
    {
        "name": "get_option_chain",
        "description": "Fetch the option chain for an underlying symbol.",
        "input_schema": {
            "type": "object",
            "properties": {
                "symbol": {"type": "string"},
                "expiry": {"type": "integer", "description": "Expiry index or identifier; optional."},
            },
            "required": ["symbol"],
        },
    },
    {
        "name": "get_positions",
        "description": "List the session's current open positions.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "get_portfolio",
        "description": "Summarise portfolio state: position count, total PnL, gross exposure.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "get_risk_status",
        "description": (
            "Report risk headroom and kill-switch state before placing orders."
        ),
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "place_order",
        "description": (
            "Place a buy/sell order via the normal session path. Set dry_run=true "
            "to preview the order (including risk headroom) without placing it."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "symbol": {"type": "string"},
                "exchange": {"type": "string"},
                "side": {"type": "string", "description": "BUY or SELL."},
                "quantity": {"type": "integer"},
                "order_type": {"type": "string", "description": "MARKET, LIMIT, etc.", "default": "MARKET"},
                "price": {"type": "number", "description": "Required for LIMIT; omit for MARKET."},
                "dry_run": {
                    "type": "boolean",
                    "description": "Preview only, do not place.",
                    "default": False,
                },
            },
            "required": ["symbol", "exchange", "side", "quantity"],
        },
    },
    {
        "name": "cancel_order",
        "description": "Cancel an open order by its order id.",
        "input_schema": {
            "type": "object",
            "properties": {"order_id": {"type": "string"}},
            "required": ["order_id"],
        },
    },
    {
        "name": "modify_order",
        "description": "Modify an open order (e.g. price, quantity, order_type).",
        "input_schema": {
            "type": "object",
            "properties": {
                "order_id": {"type": "string"},
                "price": {"type": "number"},
                "quantity": {"type": "integer"},
                "order_type": {"type": "string"},
            },
            "required": ["order_id"],
        },
    },
    {
        "name": "diagnose",
        "description": (
            "Run the broker doctor pre-flight (connectivity, auth, data access, "
            "order permissions) for a broker and return the structured report. "
            "Use this to self-diagnose the environment before live actions."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "broker": {
                    "type": "string",
                    "description": "Broker id to diagnose, e.g. paper, dhan, upstox.",
                    "default": "paper",
                },
            },
            "required": [],
        },
    },
    {
        "name": "diagnose_stream",
        "description": (
            "Run the broker streaming/subscription diagnostic to verify a live "
            "market-data stream can be opened. Returns the Subscription check result "
            "plus the full diagnostic check set."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "broker": {
                    "type": "string",
                    "description": "Broker id to diagnose, e.g. paper, dhan, upstox.",
                    "default": "paper",
                },
            },
            "required": [],
        },
    },
    {
        "name": "check_readiness",
        "description": (
            "Report platform readiness using the same gate as the /ready endpoint: "
            "event bus, OMS context, reconciliation gate, broker session. Use this to "
            "self-diagnose whether the platform is ready to serve traffic."
        ),
        "input_schema": {"type": "object", "properties": {}},
    },
]


def build_tool_schemas() -> list[dict[str, Any]]:
    """Return the Anthropic tool definitions for the agent surface."""
    return [dict(spec) for spec in AGENT_TOOL_SPECS]


def dispatch_tool(tools: AgentTools, name: str, args: dict[str, Any]) -> Any:
    """Route a tool-call request to the matching ``AgentTools`` method.

    Every name here maps 1:1 to an ``AgentTools`` method, so the existing
    guardrails (rate-limit / symbol-allowlist / dry-run) run on every call.
    """
    method = getattr(tools, name, None)
    if method is None or not callable(method):
        raise ValueError(f"Unknown agent tool: {name!r}")
    return method(**args)


__all__ = ["AGENT_TOOL_SPECS", "build_tool_schemas", "dispatch_tool"]
