"""Tests for broker common infrastructure: Capabilities, WireMapper, SymbolResolver."""

from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

import pytest

from domain.enums import AssetClass, OrderSide, OrderStatus, OrderType, TimeInForce
from domain.messages import OrderCommand
from domain.value_objects import CorrelationId, InstrumentId, OrderId, Price, Quantity
from plugins.brokers.common.capabilities import BrokerCapabilities
from plugins.brokers.common.symbol_resolver import SymbolNotFoundError, SymbolResolver
from plugins.brokers.common.wire_mapper import WireMapper
from domain.entities import Order


class TestBrokerCapabilities:
    def test_frozen(self) -> None:
        caps = BrokerCapabilities(
            supported_asset_classes=frozenset({AssetClass.EQUITY}),
        )
        with pytest.raises(Exception):
            caps.supports_market_order = False  # type: ignore[misc]

    def test_defaults(self) -> None:
        caps = BrokerCapabilities(
            supported_asset_classes=frozenset({AssetClass.EQUITY}),
        )
        assert caps.supports_market_order is True
        assert caps.supports_limit_order is True
        assert caps.supports_stop_order is False
        assert caps.supports_modify is True
        assert caps.supports_cancel is True
        assert caps.max_order_quantity is None
        assert caps.max_order_value is None

    def test_custom_values(self) -> None:
        caps = BrokerCapabilities(
            supports_market_order=False,
            supports_limit_order=True,
            supports_stop_order=True,
            supports_modify=False,
            supports_cancel=False,
            supported_asset_classes=frozenset({AssetClass.DERIVATIVE}),
            max_order_quantity=Quantity(Decimal("1000")),
            max_order_value=Price(Decimal("100000")),
        )
        assert caps.supports_market_order is False
        assert caps.supports_stop_order is True
        assert caps.max_order_quantity == Quantity(Decimal("1000"))
        assert caps.max_order_value == Price(Decimal("100000"))


class TestWireMapper:
    def _make_mapper(self) -> WireMapper:
        return WireMapper(
            field_map={
                "symbol": "tradingsymbol",
                "side": "transaction_type",
                "order_type": "order_type",
                "quantity": "quantity",
                "price": "price",
                "time_in_force": "validity",
            },
            side_map={OrderSide.BUY: "BUY", OrderSide.SELL: "SELL"},
            order_type_map={OrderType.MARKET: "MARKET", OrderType.LIMIT: "LIMIT"},
        )

    def test_to_wire(self) -> None:
        mapper = self._make_mapper()
        cmd = OrderCommand(
            timestamp=0,
            instrument_id=InstrumentId("NSE:RELIANCE"),
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            quantity=Quantity(Decimal("10")),
            price=Price(Decimal("2500.50")),
            time_in_force=TimeInForce.DAY,
        )
        wire = mapper.to_wire(cmd, symbol="RELIANCE")
        assert wire["tradingsymbol"] == "RELIANCE"
        assert wire["transaction_type"] == "BUY"
        assert wire["order_type"] == "LIMIT"
        assert wire["quantity"] == 10
        assert wire["price"] == 2500.50
        assert wire["validity"] == "DAY"

    def test_to_wire_market_order_no_price(self) -> None:
        mapper = self._make_mapper()
        cmd = OrderCommand(
            timestamp=0,
            instrument_id=InstrumentId("NSE:RELIANCE"),
            side=OrderSide.SELL,
            order_type=OrderType.MARKET,
            quantity=Quantity(Decimal("5")),
            price=None,
            time_in_force=TimeInForce.DAY,
        )
        wire = mapper.to_wire(cmd, symbol="RELIANCE")
        assert wire["transaction_type"] == "SELL"
        assert wire["order_type"] == "MARKET"
        assert wire["quantity"] == 5
        assert wire.get("price") is None

    def test_from_wire(self) -> None:
        mapper = self._make_mapper()
        data = {
            "order_id": "12345",
            "tradingsymbol": "RELIANCE",
            "transaction_type": "BUY",
            "order_type": "LIMIT",
            "quantity": 10,
            "price": 2500.50,
            "status": "COMPLETE",
        }
        order = mapper.from_wire(data)
        assert order.order_id == OrderId("12345")
        assert order.instrument_id == InstrumentId("RELIANCE")
        assert order.side == OrderSide.BUY
        assert order.order_type == OrderType.LIMIT
        assert order.quantity == Quantity(Decimal("10"))
        assert order.price == Price(Decimal("2500.50"))
        assert order.status == OrderStatus.FILLED


class TestSymbolResolver:
    def test_resolve(self) -> None:
        resolver = SymbolResolver()
        resolver.add(InstrumentId("NSE:RELIANCE"), "RELIANCE")
        assert resolver.resolve(InstrumentId("NSE:RELIANCE")) == "RELIANCE"

    def test_lookup(self) -> None:
        resolver = SymbolResolver()
        resolver.add(InstrumentId("NSE:RELIANCE"), "RELIANCE")
        assert resolver.lookup("RELIANCE") == InstrumentId("NSE:RELIANCE")

    def test_resolve_not_found(self) -> None:
        resolver = SymbolResolver()
        with pytest.raises(SymbolNotFoundError):
            resolver.resolve(InstrumentId("NSE:UNKNOWN"))

    def test_lookup_not_found(self) -> None:
        resolver = SymbolResolver()
        with pytest.raises(SymbolNotFoundError):
            resolver.lookup("UNKNOWN")