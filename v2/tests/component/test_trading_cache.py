"""TradingCache: set/get quote — cache-then-read."""

from datetime import UTC, datetime
from decimal import Decimal

from application.oms.trading_cache import TradingCache
from domain.entities import Quote
from domain.value_objects import InstrumentId, Price, Quantity


def test_set_get_quote_cache_then_read() -> None:
    cache = TradingCache()
    iid = InstrumentId(value="NSE:RELIANCE")
    quote = Quote(
        instrument_id=iid,
        bid=Price(value=Decimal("2500.00")),
        ask=Price(value=Decimal("2500.50")),
        bid_size=Quantity(value=Decimal("10")),
        ask_size=Quantity(value=Decimal("12")),
        timestamp=datetime(2024, 1, 2, 9, 15, tzinfo=UTC),
    )

    assert cache.get_quote(iid) is None
    cache.set_quote(quote)
    got = cache.get_quote(iid)
    assert got is quote
    assert got.bid.value == Decimal("2500.00")


def test_snapshot_includes_orders_positions_quotes() -> None:
    cache = TradingCache()
    iid = InstrumentId(value="NSE:TCS")
    quote = Quote(
        instrument_id=iid,
        bid=Price(value=Decimal("1")),
        ask=Price(value=Decimal("2")),
        bid_size=Quantity(value=Decimal("1")),
        ask_size=Quantity(value=Decimal("1")),
        timestamp=datetime(2024, 1, 2, tzinfo=UTC),
    )
    cache.set_quote(quote)
    snap = cache.snapshot()
    assert "orders" in snap and "positions" in snap and "quotes" in snap
    assert snap["quotes"][iid.value] is quote
