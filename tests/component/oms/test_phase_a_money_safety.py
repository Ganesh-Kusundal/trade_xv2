"""Phase A money-safety redesign — integration checks (no mocks)."""

from __future__ import annotations

from decimal import Decimal

import pytest

from application.oms import OrderManager, OrderRequest, PositionManager, RiskConfig, RiskManager
from application.oms._internal.order_mutation_guard import OrderMutationGuard
from domain import Order, OrderStatus, OrderType, ProductType, Side
from domain.events.capital_events import is_capital_event
from domain.events.types import EventType
from infrastructure.event_bus.event_bus import EventBus


def _make_oms() -> tuple[OrderManager, RiskManager]:
    bus = EventBus()
    pm = PositionManager(event_bus=bus)
    rm = RiskManager(
        config=RiskConfig(),
        position_manager=pm,
        capital_fn=lambda: Decimal("1_000_000"),
    )
    om = OrderManager(event_bus=bus, risk_manager=rm)
    return om, rm


def _limit_buy() -> OrderRequest:
    return OrderRequest(
        "RELIANCE",
        "NSE",
        Side.BUY,
        10,
        price=Decimal("2500"),
        order_type=OrderType.LIMIT,
    )


def test_cancel_order_blocked_when_kill_switch_active() -> None:
    om, rm = _make_oms()

    placed = om.place_order(_limit_buy())
    assert placed.success and placed.order is not None

    rm.set_kill_switch(True)
    cancelled = om.cancel_order(placed.order.order_id)
    assert not cancelled.success
    assert cancelled.error is not None
    assert "kill switch" in cancelled.error.lower()


def test_modify_order_blocked_when_kill_switch_active() -> None:
    om, rm = _make_oms()

    placed = om.place_order(_limit_buy())
    assert placed.success and placed.order is not None

    rm.set_kill_switch(True)
    from domain.orders.requests import ModifyOrderRequest

    modified = om.modify_order(
        ModifyOrderRequest(order_id=placed.order.order_id, quantity=5)
    )
    assert not modified.success
    assert modified.error is not None
    assert "kill switch" in modified.error.lower()


def test_risk_manager_rejects_when_instrument_lookup_fails() -> None:
    pm = PositionManager()
    rm = RiskManager(
        config=RiskConfig(),
        position_manager=pm,
        instrument_provider=FailingProvider(),
    )
    order = Order(
        order_id="1",
        symbol="RELIANCE",
        exchange="NSE",
        side=Side.BUY,
        order_type=OrderType.LIMIT,
        quantity=10,
        price=Decimal("2500.50"),
        product_type=ProductType.INTRADAY,
        status=OrderStatus.OPEN,
    )
    result = rm.check_order(order)
    assert not result.allowed
    assert "instrument lookup failed" in result.reason.lower()


def test_capital_event_classification_parity_sync_and_async() -> None:
    """Sync fsync set and async never-drop set share is_capital_event()."""
    capital = EventType.ORDER_CANCELLED.value
    non_capital = EventType.TICK.value
    assert is_capital_event(capital)
    assert not is_capital_event(non_capital)
    assert is_capital_event("ORDER_CUSTOM_STATUS")
    assert is_capital_event(EventType.TRADE_APPLIED.value)


def test_order_mutation_guard_all_actions() -> None:
    pm = PositionManager()
    rm = RiskManager(config=RiskConfig(), position_manager=pm)
    guard = OrderMutationGuard(rm)
    assert guard.check("place").allowed
    rm.set_kill_switch(True)
    for action in ("place", "modify", "cancel"):
        result = guard.check(action)  # type: ignore[arg-type]
        assert not result.allowed
        assert "kill switch" in (result.reason or "").lower()


class FailingProvider:
    def resolve(self, symbol: str, exchange: str) -> None:
        raise RuntimeError("catalog unavailable")


def test_dhan_http_client_single_rate_limit_path() -> None:
    """Legacy _throttle removed — only token-bucket acquire remains."""
    from brokers.dhan.api.http_client import DhanHttpClient

    assert not hasattr(DhanHttpClient, "_throttle")


def test_analytics_provider_query_uses_pool_not_memory() -> None:
    import inspect

    from datalake.adapters.analytics_provider import DataLakeMarketDataProvider

    src = inspect.getsource(DataLakeMarketDataProvider.query)
    assert "duckdb.connect" not in src
    assert "duckdb_connection" in src
