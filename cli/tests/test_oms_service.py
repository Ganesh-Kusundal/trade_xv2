"""Tests for OmsService integration with TradingContext."""

from __future__ import annotations
from tests.conftest import build_test_trading_context

from decimal import Decimal

from application.oms.context import TradingContext
from brokers.paper.mock_broker import MockBroker
from cli.services.oms_service import OmsService


def test_oms_service_reads_from_trading_context() -> None:
    ctx = build_test_trading_context()
    broker = MockBroker(trading_context=ctx)
    service = OmsService(gateway=broker.gateway, trading_context=ctx)

    broker.place_order("RELIANCE", "NSE", "BUY", 10, price=Decimal("2500"))

    orders = service.get_orders()
    assert len(orders) == 1
    assert orders[0].symbol == "RELIANCE"

    stats = service.get_order_stats()
    assert stats["filled"] == 1


def test_oms_service_cancel_order_via_context() -> None:
    ctx = build_test_trading_context()
    broker = MockBroker(trading_context=ctx)
    service = OmsService(gateway=broker.gateway, trading_context=ctx)

    broker.place_order("RELIANCE", "NSE", "BUY", 10, price=Decimal("2500"))
    order = ctx.order_manager.get_orders()[0]

    # Filled order cannot be cancelled.
    assert not service.cancel_order(order.order_id)


def test_oms_service_gateway_fallback() -> None:
    broker = MockBroker()
    service = OmsService(gateway=broker.gateway)

    broker.place_order("RELIANCE", "NSE", "BUY", 5, price=Decimal("2500"))
    assert len(service.get_orders()) == 1
