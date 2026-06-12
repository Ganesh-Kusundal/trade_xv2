"""Live read-only integration tests for Dhan."""

from __future__ import annotations

import os
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

import pytest

from brokers.common.core.connection import Capability
from brokers.common.core.enums import ExchangeSegment

pytestmark = [
    pytest.mark.dhan,
    pytest.mark.integration,
    pytest.mark.live_readonly,
]


def test_live_connects_and_reads_profile(live_readonly_broker: Any) -> None:
    assert live_readonly_broker.is_connected()
    assert live_readonly_broker.settings.environment.upper() == "LIVE"

    profile = live_readonly_broker.portfolio.get_profile()
    assert isinstance(profile, dict)


def test_live_portfolio_retrieval(live_readonly_broker: Any) -> None:
    portfolio = live_readonly_broker.get_capability(Capability.PORTFOLIO)
    assert portfolio is not None

    positions = portfolio.get_positions()
    holdings = portfolio.get_holdings()
    funds = portfolio.get_fund_limits()

    assert isinstance(positions, list)
    assert isinstance(holdings, list)
    assert funds.available_balance >= Decimal("0")


def test_live_order_query_retrieval(live_readonly_broker: Any) -> None:
    order_query = live_readonly_broker.get_capability(Capability.ORDER_QUERY)
    assert order_query is not None

    orders = order_query.get_order_list()
    trades = order_query.get_trades()

    assert isinstance(orders, list)
    assert isinstance(trades, list)


def test_live_market_data_retrieval(live_readonly_broker: Any) -> None:
    security_id = os.getenv("DHAN_TEST_SECURITY_ID", "2885")
    exchange_segment = ExchangeSegment(
        os.getenv("DHAN_TEST_EXCHANGE_SEGMENT", ExchangeSegment.NSE.value)
    )

    quote = live_readonly_broker.get_quote(security_id, exchange_segment)
    assert quote is not None
    assert quote.security_id == security_id
    assert quote.exchange_segment == exchange_segment

    candles = live_readonly_broker.get_historical_data(
        security_id=security_id,
        exchange_segment=exchange_segment,
        from_date=date.today() - timedelta(days=10),
        to_date=date.today(),
        interval="1",
    )
    assert isinstance(candles, list)


def test_live_mutations_are_blocked(live_readonly_broker: Any) -> None:
    request = object()

    with pytest.raises(AssertionError, match="Live mutation blocked"):
        live_readonly_broker.place_order(request)

    with pytest.raises(AssertionError, match="Live mutation blocked"):
        live_readonly_broker.order_command.place_order(request)

    with pytest.raises(AssertionError, match="Live mutation blocked"):
        live_readonly_broker.order_client.place_order(request)
