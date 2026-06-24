"""Contract tests for domain ports — verifies all ports are Protocol subclasses."""

from __future__ import annotations

from typing import Protocol, get_type_hints

import pytest

from domain.ports.broker_gateway import OrderTransportPort
from domain.ports.event_publisher import EventPublisher
from domain.ports.risk_manager import RiskManagerPort


class TestDomainPortContracts:
    """Every domain port must be a runtime-checkable Protocol."""

    @pytest.mark.parametrize(
        "port_module,port_name",
        [
            ("domain.ports.broker_gateway", "OrderTransportPort"),
            ("domain.ports.event_publisher", "EventPublisher"),
            ("domain.ports.risk_manager", "RiskManagerPort"),
        ],
    )
    def test_port_is_protocol(self, port_module: str, port_name: str):
        import importlib

        module = importlib.import_module(port_module)
        port_cls = getattr(module, port_name)
        assert issubclass(port_cls, Protocol), f"{port_name} must be a Protocol subclass"

    def test_broker_gateway_has_place_order(self):
        assert hasattr(OrderTransportPort, "place_order")

    def test_broker_gateway_place_order_signature(self):
        hints = get_type_hints(OrderTransportPort.place_order)
        assert "symbol" in hints
        assert "exchange" in hints
        assert "side" in hints
        assert "quantity" in hints

    def test_event_publisher_has_publish(self):
        assert hasattr(EventPublisher, "publish")

    def test_event_publisher_has_subscribe(self):
        assert hasattr(EventPublisher, "subscribe")

    def test_risk_manager_port_exists(self):
        assert RiskManagerPort is not None
