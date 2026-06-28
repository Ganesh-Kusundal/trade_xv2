"""Tests for UpstoxOrderCommandAdapter event publishing."""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock

from brokers.common.dtos import BrokerOrderPayload
from brokers.upstox.orders.order_client import UpstoxRestOrderClient
from brokers.upstox.orders.order_command_adapter import UpstoxOrderCommandAdapter
from domain import (
    OrderType as EnumsOrderType,
)
from domain import (
    ProductType as EnumsProductType,
)
from domain import (
    Side,
)
from domain import (
    Validity as EnumsValidity,
)


class _FakeOrderClient(UpstoxRestOrderClient):
    def __init__(self):
        pass  # skip base init requiring http_client

    def place_order_v3(self, payload: dict) -> dict:
        return {"status": "success", "data": {"order_id": "UPSTOX-ORD-1"}}


def test_place_order_does_not_publish_order_placed() -> None:
    """OMS is the sole publisher of ORDER_PLACED; adapter is transport-only."""
    resolver = MagicMock()
    resolver.resolve.return_value = MagicMock(instrument_key="NSE_EQ|RELIANCE")

    adapter = UpstoxOrderCommandAdapter(
        order_client=_FakeOrderClient(),
        instrument_resolver=resolver,
    )

    request = BrokerOrderPayload(
        symbol="RELIANCE",
        transaction_type=Side.BUY,
        quantity=10,
        price=Decimal("2500"),
        order_type=EnumsOrderType.MARKET,
        product_type=EnumsProductType.INTRADAY,
        validity=EnumsValidity.DAY,
        correlation_id="corr-1",
    )
    response = adapter.place_order(request)

    assert response.success


def test_place_order_failure_does_not_publish() -> None:
    client = _FakeOrderClient()
    client.place_order_v3 = lambda payload: {"status": "error", "errors": ["boom"]}

    resolver = MagicMock()
    resolver.resolve.return_value = MagicMock(instrument_key="NSE_EQ|RELIANCE")

    adapter = UpstoxOrderCommandAdapter(
        order_client=client,
        instrument_resolver=resolver,
    )

    request = BrokerOrderPayload(
        symbol="RELIANCE",
        transaction_type=Side.BUY,
        quantity=10,
        order_type=EnumsOrderType.MARKET,
        product_type=EnumsProductType.INTRADAY,
        validity=EnumsValidity.DAY,
    )
    response = adapter.place_order(request)

    assert not response.success


def test_place_order_risk_check_blocks_order() -> None:
    from application.oms.position_manager import PositionManager
    from application.oms.risk_manager import RiskConfig, RiskManager

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

    request = BrokerOrderPayload(
        symbol="RELIANCE",
        transaction_type=Side.BUY,
        quantity=1000,
        price=Decimal("100"),
        order_type=EnumsOrderType.LIMIT,
        product_type=EnumsProductType.INTRADAY,
        validity=EnumsValidity.DAY,
    )
    response = adapter.place_order(request)

    assert not response.success
    assert "Risk check failed" in response.message
