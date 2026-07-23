"""Unit tests for OMS: OrderManager, PositionManager, TradingCache, TradingContext."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest

from application.oms.order_manager import OrderManager
from application.oms.position_manager import PositionManager
from application.oms.trading_cache import TradingCache
from application.oms.trading_context import TradingContext
from domain.entities import Order, Position, Quote, Trade
from domain.enums import OrderSide, OrderStatus, OrderType, TimeInForce
from domain.value_objects import (
    CorrelationId,
    InstrumentId,
    Money,
    OrderId,
    Price,
    Quantity,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _order_manager() -> tuple[OrderManager, TradingCache]:
    cache = TradingCache()
    return OrderManager(cache), cache


def _position_manager() -> tuple[PositionManager, TradingCache]:
    cache = TradingCache()
    return PositionManager(cache), cache


def _iid(sym: str = "RELIANCE") -> InstrumentId:
    return InstrumentId.parse(f"NSE:{sym}")


def _oid(val: str = "o1") -> OrderId:
    return OrderId(value=val)


def _buy_trade(
    sym: str = "RELIANCE",
    price: int = 100,
    qty: int = 10,
    trade_id: str = "t1",
) -> Trade:
    return Trade(
        trade_id=trade_id,
        order_id=OrderId(value="o1"),
        instrument_id=_iid(sym),
        price=Price(value=Decimal(str(price))),
        quantity=Quantity(value=Decimal(str(qty))),
        side=OrderSide.BUY,
        timestamp=datetime(2024, 1, 2, tzinfo=UTC),
    )


def _sell_trade(
    sym: str = "RELIANCE",
    price: int = 110,
    qty: int = 4,
    trade_id: str = "t2",
) -> Trade:
    return Trade(
        trade_id=trade_id,
        order_id=OrderId(value="o2"),
        instrument_id=_iid(sym),
        price=Price(value=Decimal(str(price))),
        quantity=Quantity(value=Decimal(str(qty))),
        side=OrderSide.SELL,
        timestamp=datetime(2024, 1, 2, 10, tzinfo=UTC),
    )


def _create_order(
    om: OrderManager,
    oid: str = "o1",
    sym: str = "RELIANCE",
    side: OrderSide = OrderSide.BUY,
    qty: int = 10,
    price: int | None = 2500,
) -> Order:
    return om.create_pending(
        order_id=_oid(oid),
        instrument_id=_iid(sym),
        side=side,
        order_type=OrderType.LIMIT if price is not None else OrderType.MARKET,
        quantity=Quantity(value=Decimal(str(qty))),
        price=Price(value=Decimal(str(price))) if price is not None else None,
        time_in_force=TimeInForce.DAY,
        correlation_id=CorrelationId(value=uuid4()),
    )


# ===========================================================================
# TradingCache
# ===========================================================================

class TestTradingCache:
    def test_get_order_returns_none_when_empty(self) -> None:
        cache = TradingCache()
        assert cache.get_order(_oid()) is None

    def test_set_and_get_order(self) -> None:
        cache = TradingCache()
        order = _create_order(OrderManager(cache), oid="c1")
        got = cache.get_order(_oid("c1"))
        assert got is order

    def test_get_order_by_string_key(self) -> None:
        cache = TradingCache()
        order = _create_order(OrderManager(cache), oid="c2")
        got = cache.get_order("c2")
        assert got is order

    def test_get_position_returns_none_when_empty(self) -> None:
        cache = TradingCache()
        assert cache.get_position(_iid()) is None

    def test_set_and_get_position(self) -> None:
        cache = TradingCache()
        pos = Position(
            instrument_id=_iid(),
            quantity=Quantity(value=Decimal("10")),
            avg_price=Price(value=Decimal("100")),
            realized_pnl=Money(amount=Decimal("0"), currency="INR"),
            unrealized_pnl=Money(amount=Decimal("0"), currency="INR"),
        )
        cache.set_position(pos)
        assert cache.get_position(_iid()) is pos

    def test_get_position_by_string_key(self) -> None:
        cache = TradingCache()
        pos = Position(
            instrument_id=_iid(),
            quantity=Quantity(value=Decimal("5")),
            avg_price=Price(value=Decimal("200")),
            realized_pnl=Money(amount=Decimal("0"), currency="INR"),
            unrealized_pnl=Money(amount=Decimal("0"), currency="INR"),
        )
        cache.set_position(pos)
        assert cache.get_position("NSE:RELIANCE") is pos

    def test_set_and_get_quote(self) -> None:
        cache = TradingCache()
        quote = Quote(
            instrument_id=_iid(),
            bid=Price(value=Decimal("99")),
            ask=Price(value=Decimal("101")),
            bid_size=Quantity(value=Decimal("5")),
            ask_size=Quantity(value=Decimal("3")),
            timestamp=datetime(2024, 1, 2, tzinfo=UTC),
        )
        cache.set_quote(quote)
        assert cache.get_quote(_iid()) is quote

    def test_snapshot_returns_all_three_maps(self) -> None:
        cache = TradingCache()
        snap = cache.snapshot()
        assert set(snap) == {"orders", "positions", "quotes"}
        assert isinstance(snap["orders"], dict)
        assert isinstance(snap["positions"], dict)
        assert isinstance(snap["quotes"], dict)

    def test_order_overwrite_on_same_id(self) -> None:
        cache = TradingCache()
        om = OrderManager(cache)
        o1 = _create_order(om, oid="ow1")
        o2 = _create_order(om, oid="ow1")
        assert o1 is not o2
        assert cache.get_order(_oid("ow1")) is o2


# ===========================================================================
# OrderManager
# ===========================================================================

class TestOrderManager:
    def test_create_pending_stores_order_in_cache(self) -> None:
        om, cache = _order_manager()
        order = _create_order(om)
        assert order.status is OrderStatus.PENDING
        assert cache.get_order(_oid()) is order

    def test_apply_submitted_transitions_to_submitted(self) -> None:
        om, cache = _order_manager()
        _create_order(om)
        result = om.apply_submitted(_oid())
        assert result.status is OrderStatus.SUBMITTED
        assert cache.get_order(_oid()).status is OrderStatus.SUBMITTED

    def test_apply_submitted_returns_new_order_instance(self) -> None:
        om, cache = _order_manager()
        original = _create_order(om)
        submitted = om.apply_submitted(_oid())
        assert submitted is not original
        assert original.status is OrderStatus.PENDING

    def test_full_lifecycle_pending_to_filled(self) -> None:
        om, cache = _order_manager()
        _create_order(om, qty=10)
        om.apply_submitted(_oid())
        om.apply_fill(_oid(), filled_qty=Quantity(value=Decimal("5")))
        partial = cache.get_order(_oid())
        assert partial.status is OrderStatus.PARTIALLY_FILLED
        assert partial.filled_quantity.value == Decimal("5")

        om.apply_fill(_oid(), filled_qty=Quantity(value=Decimal("5")))
        filled = cache.get_order(_oid())
        assert filled.status is OrderStatus.FILLED
        assert filled.filled_quantity.value == Decimal("10")

    def test_fill_raises_when_qty_exceeds_order(self) -> None:
        om, _ = _order_manager()
        _create_order(om, qty=5)
        om.apply_submitted(_oid())
        with pytest.raises(ValueError, match="exceeds order qty"):
            om.apply_fill(_oid(), filled_qty=Quantity(value=Decimal("6")))

    def test_illegal_transition_pending_to_cancelled(self) -> None:
        om, _ = _order_manager()
        _create_order(om)
        with pytest.raises(ValueError, match="illegal transition"):
            om.apply_cancel(_oid())

    def test_illegal_transition_pending_to_filled(self) -> None:
        om, _ = _order_manager()
        _create_order(om)
        with pytest.raises(ValueError, match="illegal transition"):
            om.apply_fill(_oid(), filled_qty=Quantity(value=Decimal("10")))

    @pytest.mark.parametrize(
        "method_name,target_status",
        [
            ("apply_cancel", OrderStatus.CANCELLED),
            ("apply_reject", OrderStatus.REJECTED),
            ("apply_unknown", OrderStatus.UNKNOWN),
        ],
    )
    def test_transitions_from_submitted(
        self, method_name: str, target_status: OrderStatus
    ) -> None:
        om, cache = _order_manager()
        _create_order(om, oid=f"t_{target_status.name}")
        om.apply_submitted(Oid := _oid(f"t_{target_status.name}"))
        result = getattr(om, method_name)(_oid(f"t_{target_status.name}"))
        assert result.status is target_status
        assert cache.get_order(_oid(f"t_{target_status.name}")).status is target_status

    def test_partial_fill_then_cancel(self) -> None:
        om, cache = _order_manager()
        _create_order(om, qty=10)
        om.apply_submitted(_oid())
        om.apply_fill(_oid(), filled_qty=Quantity(value=Decimal("3")))
        assert cache.get_order(_oid()).status is OrderStatus.PARTIALLY_FILLED
        om.apply_cancel(_oid())
        assert cache.get_order(_oid()).status is OrderStatus.CANCELLED

    def test_get_order_raises_keyerror_when_missing(self) -> None:
        om, _ = _order_manager()
        with pytest.raises(KeyError, match="not found"):
            om.get_order(_oid("nope"))

    def test_filled_order_is_terminal_no_further_transitions(self) -> None:
        om, _ = _order_manager()
        _create_order(om, qty=1)
        om.apply_submitted(_oid())
        om.apply_fill(_oid(), filled_qty=Quantity(value=Decimal("1")))
        with pytest.raises(ValueError, match="illegal transition"):
            om.apply_cancel(_oid())


# ===========================================================================
# PositionManager
# ===========================================================================

class TestPositionManager:
    def test_buy_creates_position_with_correct_qty_and_avg(self) -> None:
        pm, cache = _position_manager()
        pos = pm.apply_trade(_buy_trade())
        assert pos.quantity.value == Decimal("10")
        assert pos.avg_price.value == Decimal("100")
        assert pos.realized_pnl.amount == Decimal("0")
        assert cache.get_position(_iid()) is pos

    def test_second_buy_increases_qty_and_updates_avg(self) -> None:
        pm, _ = _position_manager()
        pm.apply_trade(_buy_trade(price=100, qty=10, trade_id="t1"))
        pos = pm.apply_trade(
            Trade(
                trade_id="t3",
                order_id=OrderId(value="o3"),
                instrument_id=_iid(),
                price=Price(value=Decimal("120")),
                quantity=Quantity(value=Decimal("5")),
                side=OrderSide.BUY,
                timestamp=datetime(2024, 1, 3, tzinfo=UTC),
            )
        )
        # 10@100 + 5@120 → avg = (1000+600)/15 = 106.666...
        assert pos.quantity.value == Decimal("15")
        assert float(pos.avg_price.value) == pytest.approx(106.666666, rel=1e-4)

    def test_sell_reduces_position_and_realizes_pnl(self) -> None:
        pm, _ = _position_manager()
        pm.apply_trade(_buy_trade(price=100, qty=10))
        pos = pm.apply_trade(_sell_trade(price=110, qty=4))
        assert pos.quantity.value == Decimal("6")
        assert pos.avg_price.value == Decimal("100")
        assert pos.realized_pnl == Money(amount=Decimal("40"), currency="INR")

    def test_sell_entire_position_closes_to_zero(self) -> None:
        pm, _ = _position_manager()
        pm.apply_trade(_buy_trade(price=100, qty=10))
        pos = pm.apply_trade(_sell_trade(price=120, qty=10))
        assert pos.quantity.value == Decimal("0")
        assert pos.avg_price.value == Decimal("0")
        assert pos.realized_pnl == Money(amount=Decimal("200"), currency="INR")

    def test_flip_from_long_to_short(self) -> None:
        pm, _ = _position_manager()
        pm.apply_trade(_buy_trade(price=100, qty=5))
        pos = pm.apply_trade(_sell_trade(price=110, qty=10))
        assert pos.quantity.value == Decimal("-5")
        assert pos.avg_price.value == Decimal("110")
        assert pos.realized_pnl == Money(amount=Decimal("50"), currency="INR")

    def test_sell_short_then_buy_back(self) -> None:
        pm, _ = _position_manager()
        pm.apply_trade(
            Trade(
                trade_id="t1",
                order_id=OrderId(value="o1"),
                instrument_id=_iid(),
                price=Price(value=Decimal("110")),
                quantity=Quantity(value=Decimal("5")),
                side=OrderSide.SELL,
                timestamp=datetime(2024, 1, 2, tzinfo=UTC),
            )
        )
        pos = pm.apply_trade(
            Trade(
                trade_id="t2",
                order_id=OrderId(value="o2"),
                instrument_id=_iid(),
                price=Price(value=Decimal("105")),
                quantity=Quantity(value=Decimal("3")),
                side=OrderSide.BUY,
                timestamp=datetime(2024, 1, 2, 10, tzinfo=UTC),
            )
        )
        assert pos.quantity.value == Decimal("-2")
        assert pos.realized_pnl == Money(amount=Decimal("15"), currency="INR")

    def test_flip_from_short_to_long(self) -> None:
        pm, _ = _position_manager()
        pm.apply_trade(
            Trade(
                trade_id="t1",
                order_id=OrderId(value="o1"),
                instrument_id=_iid(),
                price=Price(value=Decimal("110")),
                quantity=Quantity(value=Decimal("5")),
                side=OrderSide.SELL,
                timestamp=datetime(2024, 1, 2, tzinfo=UTC),
            )
        )
        pos = pm.apply_trade(
            Trade(
                trade_id="t2",
                order_id=OrderId(value="o2"),
                instrument_id=_iid(),
                price=Price(value=Decimal("100")),
                quantity=Quantity(value=Decimal("10")),
                side=OrderSide.BUY,
                timestamp=datetime(2024, 1, 2, 10, tzinfo=UTC),
            )
        )
        assert pos.quantity.value == Decimal("5")
        assert pos.avg_price.value == Decimal("100")
        assert pos.realized_pnl == Money(amount=Decimal("50"), currency="INR")

    def test_multiple_instruments_tracked_separately(self) -> None:
        pm, _ = _position_manager()
        pm.apply_trade(_buy_trade(sym="RELIANCE", price=100, qty=10))
        pm.apply_trade(_buy_trade(sym="TCS", price=200, qty=5))
        r = pm._cache.get_position(_iid("RELIANCE"))
        t = pm._cache.get_position(_iid("TCS"))
        assert r.quantity.value == Decimal("10")
        assert t.quantity.value == Decimal("5")


# ===========================================================================
# TradingContext
# ===========================================================================

class TestTradingContext:
    def test_holds_cache_reference(self) -> None:
        cache = TradingCache()
        ctx = TradingContext(cache=cache)
        assert ctx.cache is cache

    def test_bus_defaults_to_none(self) -> None:
        ctx = TradingContext(cache=TradingCache())
        assert ctx.bus is None

    def test_holds_bus_when_provided(self) -> None:
        bus = object()
        ctx = TradingContext(cache=TradingCache(), bus=bus)
        assert ctx.bus is bus

    def test_creates_with_different_caches(self) -> None:
        c1, c2 = TradingCache(), TradingCache()
        ctx1 = TradingContext(cache=c1)
        ctx2 = TradingContext(cache=c2)
        assert ctx1.cache is not ctx2.cache
