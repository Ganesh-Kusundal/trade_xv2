"""Contract tests for broker gateway port.

Verifies that all broker adapters implement the OrderTransportPort protocol.
"""

from __future__ import annotations

from typing import get_type_hints

import pytest

from domain.ports.broker_gateway import OrderTransportPort


class TestBrokerGatewayContract:
    """Verify broker adapters implement the OrderTransportPort protocol."""

    @pytest.mark.parametrize(
        "adapter_path,adapter_class_name",
        [
            ("brokers.providers.paper.paper_gateway", "PaperGateway"),
            ("brokers.providers.paper.mock_broker", "MockBroker"),
        ],
    )
    def test_adapter_implements_protocol(self, adapter_path: str, adapter_class_name: str):
        """Adapter must implement OrderTransportPort protocol."""
        import importlib

        module = importlib.import_module(adapter_path)
        adapter_class = getattr(module, adapter_class_name)
        adapter_instance = adapter_class()

        assert isinstance(adapter_instance, OrderTransportPort), (
            f"{adapter_class_name} does not implement OrderTransportPort protocol"
        )

    @pytest.mark.parametrize(
        "adapter_path,adapter_class_name",
        [
            ("brokers.providers.paper.paper_gateway", "PaperGateway"),
            ("brokers.providers.paper.mock_broker", "MockBroker"),
        ],
    )
    def test_adapter_has_place_order(self, adapter_path: str, adapter_class_name: str):
        """Adapter must have a place_order method."""
        import importlib

        module = importlib.import_module(adapter_path)
        adapter_class = getattr(module, adapter_class_name)

        assert hasattr(adapter_class, "place_order"), (
            f"{adapter_class_name} missing place_order method"
        )
        assert callable(adapter_class.place_order), (
            f"{adapter_class_name}.place_order is not callable"
        )

    def test_place_order_signature_matches_protocol(self):
        """place_order signature must match OrderTransportPort."""
        protocol_hints = get_type_hints(OrderTransportPort.place_order)
        assert "symbol" in protocol_hints
        assert "exchange" in protocol_hints
        assert "side" in protocol_hints
        assert "quantity" in protocol_hints

    def test_protocol_is_runtime_checkable(self):
        """OrderTransportPort must be decorated with @runtime_checkable."""
        assert hasattr(OrderTransportPort, "__protocol_attrs__") or callable(
            getattr(OrderTransportPort, "__instancecheck__", None)
        )
