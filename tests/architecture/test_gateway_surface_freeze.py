"""Wave D review gate: gateway public method sets must not grow silently.

New broker *product* features belong on ports / extensions / Instrument —
not as new methods on fat gateway facades. If a public method is truly
required on a gateway (ops/transport), update the frozen allowlist in this
file in the same PR and document why.

See reports/BROKERS_EVOLUTION_PLAN.md Wave D.
"""

from __future__ import annotations

import inspect

# Frozen allowlists = methods defined on the class body (not inherited).
# Captured 2026-07-09. Growth requires explicit PR review.
_DHAN_PUBLIC = frozenset(
    {
        "cancel_all_orders",
        "cancel_order",
        "capabilities",
        "close",
        "depth",
        "depth_20",
        "depth_200",
        "describe",
        "funds",
        "future_chain",
        "get_order",
        "get_orderbook",
        "get_trade_book",
        "history",
        "history_batch",
        "holdings",
        "list_capabilities",
        "load_instruments",
        "ltp",
        "ltp_batch",
        "modify_order",
        "option_chain",
        "place_order",
        "positions",
        "quote",
        "quote_batch",
        "search",
        "stream",
        "trades",
    }
)

_UPSTOX_PUBLIC = frozenset(
    {
        "cancel_order",
        "capabilities",
        "close",
        "depth",
        "describe",
        "funds",
        "future_chain",
        "get_circuit_breaker_states",
        "get_connection_status",
        "get_order",
        "get_orderbook",
        "get_rate_limiter_metrics",
        "get_token_refresh_metrics",
        "get_trade_book",
        "history",
        "holdings",
        "load_instruments",
        "ltp",
        "ltp_batch",
        "modify_order",
        "option_chain",
        "place_order",
        "positions",
        "quote",
        "quote_batch",
        "search",
        "stream",
        "stream_depth",
        "stream_order",
        "trades",
        "unstream",
    }
)

_PAPER_PUBLIC = frozenset(
    {
        "cancel_order",
        "capabilities",
        "close",
        "depth",
        "describe",
        "funds",
        "future_chain",
        "get_order",
        "get_orderbook",
        "get_trade_book",
        "history",
        "holdings",
        "list_capabilities",
        "load_instruments",
        "ltp",
        "modify_order",
        "option_chain",
        "place_order",
        "positions",
        "quote",
        "search",
        "seed_holdings",
        "seed_orders",
        "seed_positions",
        "seed_trades",
        "stream",
        "stream_depth",
        "stream_order",
        "trades",
    }
)


def _class_body_public_methods(cls: type) -> set[str]:
    """Public functions defined on the class itself (not bases)."""
    names: set[str] = set()
    for name, obj in cls.__dict__.items():
        if name.startswith("_"):
            continue
        if inspect.isfunction(obj):
            names.add(name)
    return names


def test_dhan_gateway_public_surface_frozen():
    from brokers.dhan.gateway import DhanBrokerGateway

    actual = _class_body_public_methods(DhanBrokerGateway)
    extra = actual - _DHAN_PUBLIC
    missing = _DHAN_PUBLIC - actual
    assert not extra, (
        f"DhanBrokerGateway gained public methods {sorted(extra)}. "
        "Prefer ports/extensions; if required, update _DHAN_PUBLIC in this test."
    )
    assert not missing, (
        f"DhanBrokerGateway lost methods {sorted(missing)} — update freeze if intentional."
    )


def test_upstox_gateway_public_surface_frozen():
    from brokers.upstox.gateway import UpstoxBrokerGateway

    actual = _class_body_public_methods(UpstoxBrokerGateway)
    extra = actual - _UPSTOX_PUBLIC
    assert not extra, (
        f"UpstoxBrokerGateway gained public methods {sorted(extra)}. "
        "Prefer ports/extensions; if required, update _UPSTOX_PUBLIC."
    )


def test_paper_gateway_public_surface_frozen():
    from brokers.paper.paper_gateway import PaperGateway

    actual = _class_body_public_methods(PaperGateway)
    extra = actual - _PAPER_PUBLIC
    assert not extra, (
        f"PaperGateway gained public methods {sorted(extra)}. "
        "Prefer ports/extensions; if required, update _PAPER_PUBLIC."
    )


def test_dhan_broker_gateway_alias():
    from brokers.dhan.gateway import DhanBrokerGateway

    assert DhanBrokerGateway is DhanBrokerGateway
