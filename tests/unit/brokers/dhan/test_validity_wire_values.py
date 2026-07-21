"""Dhan order placement maps Validity enum to wire payload."""

from __future__ import annotations

from decimal import Decimal

from brokers.dhan.execution.order_placement import OrderPlacer
from domain import OrderType, ProductType, Validity
from domain.models.dtos import BrokerOrderPayload


def test_build_order_payload_maps_ioc_validity():
    request = BrokerOrderPayload(
        symbol="RELIANCE",
        exchange="NSE",
        transaction_type="BUY",
        quantity=1,
        order_type=OrderType.LIMIT,
        product_type=ProductType.INTRADAY,
        validity=Validity.IOC,
        price=Decimal("100"),
    )
    ot, pt, vl = OrderPlacer._canonicalize_order_enums(request, "NSE_EQ")
    assert vl == "IOC"
    assert ot == "LIMIT"
    assert pt == "INTRADAY"
