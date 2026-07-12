from datetime import datetime, timezone
from application.execution.trading_cache import TradingCache
from domain import Order
from domain.enums import OrderStatus
from domain.types import Side, OrderType, ProductType, Validity
from domain.state_machine import IllegalTransitionError
import pytest


def _make_order(order_id: str = "test-1", status: OrderStatus = OrderStatus.OPEN, correlation_id: str | None = None) -> Order:
    return Order(
        order_id=order_id, symbol="RELIANCE", exchange="NSE",
        side=Side.BUY, order_type=OrderType.LIMIT, quantity=10,
        price=2500.0, trigger_price=0.0, product_type=ProductType.CNC,
        validity=Validity.DAY, status=status, timestamp=datetime.now(timezone.utc),
        correlation_id=correlation_id,
    )


def test_upsert_and_get_order():
    cache = TradingCache()
    order = _make_order()
    cache.upsert_order(order)
    assert cache.get_order("test-1") is order


def test_get_order_by_correlation():
    cache = TradingCache()
    order = _make_order(correlation_id="corr-1")
    cache.upsert_order(order)
    assert cache.get_order_by_correlation("corr-1") is order


def test_update_order_status():
    cache = TradingCache()
    order = _make_order()
    cache.upsert_order(order)
    updated = cache.update_order_status("test-1", OrderStatus.FILLED)
    assert updated is not None
    assert updated.status == OrderStatus.FILLED
    assert cache.get_order("test-1").status == OrderStatus.FILLED


def test_update_order_status_fsm_validated():
    cache = TradingCache()
    order = _make_order(status=OrderStatus.FILLED)
    cache.upsert_order(order)
    with pytest.raises(IllegalTransitionError):
        cache.update_order_status("test-1", OrderStatus.OPEN)


def test_remove_order():
    cache = TradingCache()
    order = _make_order(correlation_id="corr-1")
    cache.upsert_order(order)
    removed = cache.remove_order("test-1")
    assert removed is order
    assert cache.get_order("test-1") is None
    assert cache.get_order_by_correlation("corr-1") is None


def test_all_orders():
    cache = TradingCache()
    cache.upsert_order(_make_order("o1"))
    cache.upsert_order(_make_order("o2"))
    assert len(cache.all_orders()) == 2


def test_quotes():
    cache = TradingCache()
    cache.set_quote("RELIANCE", {"ltp": 2500.0})
    assert cache.get_quote("RELIANCE") == {"ltp": 2500.0}
    assert cache.get_quote("UNKNOWN") is None


def test_positions():
    cache = TradingCache()
    cache.upsert_position("RELIANCE:NSE", {"qty": 10, "avg_price": 2500.0})
    assert cache.get_position("RELIANCE:NSE") == {"qty": 10, "avg_price": 2500.0}
    assert len(cache.all_positions()) == 1


def test_clear():
    cache = TradingCache()
    cache.upsert_order(_make_order())
    cache.set_quote("X", {})
    cache.upsert_position("Y", {})
    cache.clear()
    assert len(cache.all_orders()) == 0
    assert cache.get_quote("X") is None
    assert cache.get_position("Y") is None
