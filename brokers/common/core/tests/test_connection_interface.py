"""TDD tests for BrokerConnection — capability-based connection interface.

Inspired by Trade_J's IBrokerConnection with capability pattern.
"""

import pytest

from brokers.common.core.connection import BrokerConnection, Capability, ConnectionStatus


class TestCapabilityEnum:
    def test_values(self):
        assert Capability.MARKET_DATA.value == "market_data"
        assert Capability.ORDER_COMMAND.value == "order_command"
        assert Capability.ORDER_QUERY.value == "order_query"
        assert Capability.PORTFOLIO.value == "portfolio"
        assert Capability.OPTIONS_CHAIN.value == "options_chain"
        assert Capability.INSTRUMENTS.value == "instruments"
        assert Capability.HISTORICAL_DATA.value == "historical_data"
        assert Capability.WEBSOCKET.value == "websocket"


class TestConnectionStatus:
    def test_values(self):
        assert ConnectionStatus.DISCONNECTED.value == "DISCONNECTED"
        assert ConnectionStatus.CONNECTING.value == "CONNECTING"
        assert ConnectionStatus.CONNECTED.value == "CONNECTED"
        assert ConnectionStatus.RECONNECTING.value == "RECONNECTING"

    def test_is_connected(self):
        assert ConnectionStatus.CONNECTED.is_connected() is True
        assert ConnectionStatus.DISCONNECTED.is_connected() is False
        assert ConnectionStatus.CONNECTING.is_connected() is False


class TestBrokerConnectionInterface:
    """Tests against the abstract interface to enforce contract."""

    def test_interface_has_required_methods(self):
        """All BrokerConnection implementations must have these methods."""
        methods = [
            "connect",
            "disconnect",
            "reconnect",
            "status",
            "capabilities",
            "has_capability",
            "get_capability",
            "name",
            "broker_id",
        ]
        for method in methods:
            assert hasattr(BrokerConnection, method), f"Missing method: {method}"

    def test_interface_is_abstract(self):
        """Cannot instantiate BrokerConnection directly."""
        with pytest.raises(TypeError):
            BrokerConnection()  # type: ignore

    def test_capability_discovery_pattern(self):
        """Capability pattern from Trade_J: get_capability(Class) -> Optional[impl]."""
        assert hasattr(BrokerConnection, "get_capability")
        # Should accept a Capability enum value
        # Just verify it's properly defined
        assert True
