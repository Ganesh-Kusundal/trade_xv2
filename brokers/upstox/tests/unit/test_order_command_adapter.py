"""Tests for UpstoxOrderCommandAdapter event publishing."""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock

from brokers.common.core.domain import (
    ExchangeSegment,
    OrderType as EnumsOrderType,
    ProductType as EnumsProductType,
    TransactionType,
    Validity as EnumsValidity,
)
from brokers.common.core.domain import OrderRequest
from brokers.common.event_bus import EventBus
from brokers.upstox.orders.order_client import UpstoxRestOrderClient
from brokers.upstox.orders.order_command_adapter import UpstoxOrderCommandAdapter


class _FakeOrderClient(UpstoxRestOrderClient):
    def __init__(self):
        pass  # skip base init requiring http_client

    def place_order_v3(self, payload: dict) -> dict:
        return {"status": "success", "data": {"order_id": "UPSTOX-ORD-1"}}


def test_place_order_publishes_event() -> None:
    bus = EventBus()
    received = []
    bus.subscribe("ORDER_PLACED", lambda e: received.append(e))

    resolver = MagicMock()
    resolver.resolve.return_value = MagicMock(instrument_key="NSE_EQ|RELIANCE")

    adapter = UpstoxOrderCommandAdapter(
        order_client=_FakeOrderClient(),
        instrument_resolver=resolver,
        event_bus=bus,
    )

    request = OrderRequest(
        symbol="RELIANCE",
        exchange_segment=ExchangeSegment.NSE,
        transaction_type=TransactionType.BUY,
        quantity=10,
        price=Decimal("2500"),
        order_type=EnumsOrderType.MARKET,
        product_type=EnumsProductType.INTRADAY,
        validity=EnumsValidity.DAY,
        correlation_id="corr-1",
    )
    response = adapter.place_order(request)

    assert response.success
    assert len(received) == 1
    order = received[0].payload["order"]
    assert order.order_id == "UPSTOX-ORD-1"
    assert order.symbol == "RELIANCE"


def test_place_order_failure_does_not_publish() -> None:
    bus = EventBus()
    received = []
    bus.subscribe("ORDER_PLACED", lambda e: received.append(e))

    client = _FakeOrderClient()
    client.place_order_v3 = lambda payload: {"status": "error", "errors": ["boom"]}

    resolver = MagicMock()
    resolver.resolve.return_value = MagicMock(instrument_key="NSE_EQ|RELIANCE")

    adapter = UpstoxOrderCommandAdapter(
        order_client=client,
        instrument_resolver=resolver,
        event_bus=bus,
    )

    request = OrderRequest(
        symbol="RELIANCE",
        exchange_segment=ExchangeSegment.NSE,
        transaction_type=TransactionType.BUY,
        quantity=10,
        order_type=EnumsOrderType.MARKET,
        product_type=EnumsProductType.INTRADAY,
        validity=EnumsValidity.DAY,
    )
    response = adapter.place_order(request)

    assert not response.success
    assert len(received) == 0


def test_place_order_risk_check_blocks_order() -> None:
    from brokers.common.oms.position_manager import PositionManager
    from brokers.common.oms.risk_manager import RiskConfig, RiskManager

    resolver = MagicMock()
    resolver.resolve.return_value = MagicMock(instrument_key="NSE_EQ|RELIANCE")

    position_manager = PositionManager()
    risk = RiskManager(
        position_manager,
        RiskConfig(max_position_pct=Decimal("1")),
        lambda: Decimal("100000"),
    )
    adapter = UpstoxOrderCommandAdapter(
        order_client=_FakeOrderClient(),
        instrument_resolver=resolver,
        risk_manager=risk,
    )

    request = OrderRequest(
        symbol="RELIANCE",
        exchange_segment=ExchangeSegment.NSE,
        transaction_type=TransactionType.BUY,
        quantity=1000,
        price=Decimal("100"),
        order_type=EnumsOrderType.LIMIT,
        product_type=EnumsProductType.INTRADAY,
        validity=EnumsValidity.DAY,
    )
    response = adapter.place_order(request)

    assert not response.success
    assert "Risk check failed" in response.message
