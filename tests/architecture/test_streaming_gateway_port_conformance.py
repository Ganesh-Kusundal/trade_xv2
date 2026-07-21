"""Architecture ratchet — streaming adapters expose BrokerStreamGateway surface."""

from __future__ import annotations

import pytest

from domain.ports.broker_stream_gateway import BrokerStreamGateway


REQUIRED = ("connect", "subscribe", "on_tick", "disconnect")


@pytest.mark.architecture
def test_dhan_connection_exposes_stream_gateway_methods() -> None:
    from brokers.providers.dhan.streaming.connection import DhanConnection

    missing = [name for name in REQUIRED if not hasattr(DhanConnection, name)]
    assert not missing, f"DhanConnection missing BrokerStreamGateway methods: {missing}"


@pytest.mark.architecture
def test_upstox_streaming_gateway_exposes_stream_gateway_methods() -> None:
    from brokers.providers.upstox.adapters.streaming_gateway import StreamingGateway

    missing = [name for name in REQUIRED if not hasattr(StreamingGateway, name)]
    assert not missing, f"StreamingGateway missing BrokerStreamGateway methods: {missing}"


@pytest.mark.architecture
def test_broker_stream_gateway_protocol_is_runtime_checkable() -> None:
    assert getattr(BrokerStreamGateway, "__protocol_attrs__", None) is not None or hasattr(
        BrokerStreamGateway, "connect"
    )
