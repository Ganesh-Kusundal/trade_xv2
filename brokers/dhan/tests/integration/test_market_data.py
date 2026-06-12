"""Live data integration tests for Dhan."""

from __future__ import annotations

import os
import time
from datetime import date, timedelta
from typing import Any

import pytest

from brokers.common.core.enums import ExchangeSegment

pytestmark = [
    pytest.mark.dhan,
    pytest.mark.integration,
    pytest.mark.live_readonly,
]


def test_live_market_feed_rest_modes(live_readonly_broker: Any) -> None:
    security_id, exchange_segment = _test_instrument()

    ltp = live_readonly_broker.get_market_feed_ltp_rest(security_id, exchange_segment)
    time.sleep(1.1)
    quote = live_readonly_broker.get_market_feed_quote_rest(security_id, exchange_segment)
    time.sleep(1.1)
    ohlc = live_readonly_broker.get_market_feed_ohlc_rest(security_id, exchange_segment)

    assert ltp.security_id == security_id
    assert quote.security_id == security_id
    assert ohlc.security_id == security_id
    assert ltp.exchange_segment == exchange_segment
    assert quote.exchange_segment == exchange_segment
    assert ohlc.exchange_segment == exchange_segment
    assert ltp.last_price >= 0
    assert quote.last_price >= 0
    assert ohlc.last_price >= 0


def test_live_historical_daily_and_intraday(live_readonly_broker: Any) -> None:
    security_id, exchange_segment = _test_instrument()
    from_date = date.today() - timedelta(days=10)
    to_date = date.today()

    daily = live_readonly_broker.market_data.get_historical_daily(
        security_id,
        exchange_segment,
        from_date,
        to_date,
    )
    intraday = live_readonly_broker.market_data.get_historical_intraday(
        security_id,
        exchange_segment,
        from_date,
        to_date,
        interval="1",
    )

    assert isinstance(daily, list)
    assert isinstance(intraday, list)


def test_live_options_expiries_and_parsed_chain(live_readonly_broker: Any) -> None:
    underlying = os.getenv("DHAN_OPTION_UNDERLYING", "13")
    exchange_segment = ExchangeSegment(
        os.getenv("DHAN_OPTION_EXCHANGE_SEGMENT", ExchangeSegment.IDX_I.value)
    )

    expiries = live_readonly_broker.get_option_expiries_rest(
        underlying,
        exchange_segment,
    )
    assert isinstance(expiries, list)
    assert expiries, "no option expiries returned"

    for expiry in expiries[:3]:
        chain = live_readonly_broker.get_option_chain_rest(
            underlying,
            exchange_segment,
            expiry,
        )
        if chain:
            assert isinstance(chain, list)
            assert chain[0].strike >= 0
            return

    pytest.fail("option chain returned no parsed contracts for first expiries")


def test_live_market_depth(live_readonly_broker: Any) -> None:
    security_id, exchange_segment = _test_instrument()

    depth = live_readonly_broker.get_market_depth_rest(security_id, exchange_segment)

    assert depth.security_id == security_id
    assert depth.exchange_segment == exchange_segment
    assert depth.bids or depth.asks


def _test_instrument() -> tuple[str, ExchangeSegment]:
    return (
        os.getenv("DHAN_TEST_SECURITY_ID", "2885"),
        ExchangeSegment(os.getenv("DHAN_TEST_EXCHANGE_SEGMENT", ExchangeSegment.NSE.value)),
    )
