"""UI-facing broker operations — delegates to runtime.platform_bridge."""

from __future__ import annotations

from runtime.platform_bridge import (
    cancel_order,
    get_depth,
    get_funds,
    get_history,
    get_holdings,
    get_option_chain,
    get_positions,
    get_quote,
    lookup_security,
    run_certify,
)

__all__ = [
    "cancel_order",
    "get_depth",
    "get_funds",
    "get_history",
    "get_holdings",
    "get_option_chain",
    "get_positions",
    "get_quote",
    "lookup_security",
    "run_certify",
]
