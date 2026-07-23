"""BrokerAdapter protocol conformance — Dhan/Upstox/Paper gateways must all
satisfy the full extended surface (lifecycle, orders, portfolio, market data,
instruments, capabilities), not just the original order/position subset."""

from __future__ import annotations

from unittest.mock import MagicMock

from domain.ports.broker_adapter import BrokerAdapter
from plugins.brokers.dhan.config import DhanConfig
from plugins.brokers.dhan.gateway import DhanGateway
from plugins.brokers.paper.gateway import PaperGateway
from plugins.brokers.upstox.config import UpstoxConfig
from plugins.brokers.upstox.gateway import UpstoxGateway


def _fake_transport() -> MagicMock:
    t = MagicMock()
    t.get.return_value = {"data": []}
    t.post.return_value = {"data": []}
    return t


def test_dhan_gateway_satisfies_broker_adapter() -> None:
    gw = DhanGateway(config=DhanConfig(), transport=_fake_transport())
    assert isinstance(gw, BrokerAdapter)


def test_upstox_gateway_satisfies_broker_adapter() -> None:
    gw = UpstoxGateway(config=UpstoxConfig(), transport=_fake_transport())
    assert isinstance(gw, BrokerAdapter)


def test_paper_gateway_satisfies_broker_adapter() -> None:
    gw = PaperGateway()
    assert isinstance(gw, BrokerAdapter)


def test_protocol_covers_full_surface_not_just_orders() -> None:
    """Guards against the protocol silently shrinking back to the old
    order/position-only subset."""
    required = {
        "connect", "authenticate", "close",
        "submit_order", "cancel_order", "modify_order", "get_order", "get_orderbook",
        "get_positions", "get_holdings", "get_funds", "mass_status",
        "get_quote", "ltp", "depth", "history",
        "load_instruments", "search", "capabilities",
    }
    protocol_methods = {m for m in dir(BrokerAdapter) if not m.startswith("_")}
    assert required <= protocol_methods


def test_streaming_not_forced_onto_protocol() -> None:
    """Streaming isn't universal (Paper doesn't implement it) — deliberately
    excluded from the shared Protocol so Paper's conformance check above
    keeps passing."""
    protocol_methods = {m for m in dir(BrokerAdapter) if not m.startswith("_")}
    assert "stream" not in protocol_methods
    assert "stream_order" not in protocol_methods
