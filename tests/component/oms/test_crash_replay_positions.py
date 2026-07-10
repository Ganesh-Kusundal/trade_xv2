"""ENG-006: crash-replay must not apply positions for rejected trades."""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock

from domain.entities.order import Order
from domain.entities.trade import Trade
from domain.enums import OrderStatus, OrderType, ProductType, Side
from domain.events.types import DomainEvent, EventType
from infrastructure.event_bus.event_bus import EventBus
from tests.conftest import build_test_trading_context


def _order(order_id: str = "O1") -> Order:
    return Order(
        order_id=order_id,
        symbol="RELIANCE",
        exchange="NSE",
        side=Side.BUY,
        order_type=OrderType.MARKET,
        quantity=10,
        filled_quantity=0,
        price=Decimal("100"),
        status=OrderStatus.OPEN,
        product_type=ProductType.INTRADAY,
        correlation_id="c1",
    )


def _trade(order_id: str, trade_id: str) -> Trade:
    return Trade(
        trade_id=trade_id,
        order_id=order_id,
        symbol="RELIANCE",
        exchange="NSE",
        side=Side.BUY,
        quantity=10,
        price=Decimal("100"),
    )


def _trade_event(order_id: str, trade_id: str) -> DomainEvent:
    return DomainEvent.now(
        EventType.TRADE.value,
        {"trade": _trade(order_id, trade_id)},
    )


def test_replay_skips_position_when_order_unknown():
    bus = EventBus()
    event_log = MagicMock()
    event_log.replay.return_value = [_trade_event("MISSING", "T1")]

    ctx = build_test_trading_context(
        event_bus=bus,
        event_log=event_log,
        replay_events=False,
        enable_durable_orders=False,
    )
    ctx._position_manager.on_trade_applied = MagicMock(
        wraps=ctx._position_manager.on_trade_applied
    )
    ctx._replay_log_into_oms()

    ctx._position_manager.on_trade_applied.assert_not_called()
    assert len(ctx._position_manager.get_positions()) == 0


def test_replay_applies_position_when_order_known():
    bus = EventBus()
    event_log = MagicMock()
    event_log.replay.return_value = [_trade_event("O1", "T-OK")]

    ctx = build_test_trading_context(
        event_bus=bus,
        event_log=event_log,
        replay_events=False,
        enable_durable_orders=False,
    )
    ctx.order_manager._orders["O1"] = _order("O1")
    ctx._replay_log_into_oms()

    positions = ctx._position_manager.get_positions()
    assert len(positions) >= 1


def test_event_log_attached_to_bus_when_separate():
    """ENG-010: TradingContext wires event_log onto bus if missing."""
    bus = EventBus()
    assert bus._event_log is None
    log = MagicMock()
    build_test_trading_context(
        event_bus=bus,
        event_log=log,
        replay_events=False,
        enable_durable_orders=False,
    )
    assert bus._event_log is log
