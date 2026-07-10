"""Epic 1 — Market Access E2E (paper CI gate).

Product path::

    tradex.connect("paper")
      → universe.equity → refresh → history → subscribe → close

No gateway imports in the user-facing path under test.
"""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

import tradex
from domain.candles.historical import HistoricalSeries


def test_market_access_paper_quote_history_subscribe() -> None:
    """MA-S1: full paper market-access MVP."""
    session = tradex.connect("paper")
    try:
        assert session.status is not None
        assert session.status.mode == "sim"

        stock = session.universe.equity("RELIANCE")
        assert stock.symbol == "RELIANCE"
        assert stock.exchange == "NSE"

        quote = stock.refresh()
        assert quote is not None
        assert stock.ltp is not None
        assert stock.ltp > 0
        assert stock.bid is not None
        assert stock.ask is not None

        series = stock.history(timeframe="1D", days=5)
        assert isinstance(series, HistoricalSeries)
        assert series.bar_count >= 5
        assert len(series.bars) >= 5
        assert series.bars[0].close > 0

        received: list = []

        def _on_tick(iid, payload) -> None:
            received.append((iid, payload))

        handle = stock.subscribe(_on_tick)
        assert handle is not None
        assert handle.is_active is True
        assert stock.is_live is True
        # Paper delivers an initial snapshot via callback
        assert len(received) >= 1
        assert stock.ltp is not None

        handle.unsubscribe()
        assert handle.is_active is False
    finally:
        session.close()


def test_paper_history_respects_lookback_days() -> None:
    session = tradex.connect("paper")
    try:
        stock = session.universe.equity("INFY")
        series = stock.history(timeframe="1D", days=10)
        assert series.bar_count == 10
    finally:
        session.close()


def test_paper_subscribe_without_callback_still_marks_live() -> None:
    session = tradex.connect("paper")
    try:
        stock = session.universe.equity("TCS")
        handle = stock.subscribe()
        assert handle is not None
        assert stock.is_live is True
        handle.unsubscribe()
    finally:
        session.close()


def test_market_mode_connect_without_oms_orders_disabled() -> None:
    """MA-S2 unit gate: live mode=market needs no process OMS; orders fail closed."""
    mock_gw = MagicMock(name="DhanGateway")

    with patch("infrastructure.gateway.factory.create_gateway", return_value=mock_gw):
        import brokers.dhan  # noqa: F401

        session = tradex.connect("dhan", mode="market", load_instruments=False)
        try:
            assert session.status is not None
            assert session.status.mode == "market"
            assert session.status.orders_enabled is False
            assert session.order_service is None

            stock = session.universe.equity("RELIANCE")
            with pytest.raises(RuntimeError, match="ORDERS_DISABLED"):
                session.buy(stock, 1, price=Decimal("100"))
            # Instrument path uses NotConfiguredError with ORDERS_DISABLED message
            from domain.errors import NotConfiguredError

            with pytest.raises((RuntimeError, NotConfiguredError), match="ORDERS_DISABLED"):
                stock.buy(1, price=Decimal("100"))
        finally:
            session.close()
