"""Regression: Upstox wire segment maps to canonical exchange codes."""

from __future__ import annotations

from brokers.providers.upstox.mappers._base import exchange_from_wire
from domain.constants.exchanges import NFO, NSE


def test_exchange_from_wire_maps_nse_eq() -> None:
    assert exchange_from_wire("NSE_EQ") == NSE


def test_exchange_from_wire_maps_nse_fo() -> None:
    assert exchange_from_wire("NSE_FO") == NFO


def test_to_order_uses_canonical_exchange() -> None:
    from brokers.providers.upstox.mappers.derivatives_mapper import to_order

    order = to_order(
        {
            "order_id": "1",
            "trading_symbol": "RELIANCE",
            "exchange": "NSE_EQ",
            "transaction_type": "BUY",
            "quantity": 1,
            "order_type": "MARKET",
            "product": "I",
            "validity": "DAY",
            "status": "open",
        }
    )
    assert order.exchange == NSE
