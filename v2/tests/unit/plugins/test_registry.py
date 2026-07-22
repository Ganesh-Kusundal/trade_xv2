"""Broker plugin registry — register / list / get by BrokerId."""

from __future__ import annotations

import pytest

from domain.enums import BrokerId
from domain.ports import BrokerAdapterPort
from plugins.brokers.common.rate_limit import RateLimitConfig
from plugins.brokers.common.transport import BaseTransport
from plugins.brokers.registry import (
    clear_plugins,
    get_plugin,
    list_plugins,
    register_broker_plugin,
)


def test_register_list_get_plugin() -> None:
    clear_plugins()
    plugin = {"name": "paper-plugin"}
    register_broker_plugin(BrokerId.PAPER, plugin)
    assert BrokerId.PAPER in list_plugins()
    assert get_plugin(BrokerId.PAPER) is plugin


def test_get_unknown_plugin_raises() -> None:
    clear_plugins()
    with pytest.raises(KeyError):
        get_plugin(BrokerId.DHAN)


def test_rate_limit_config() -> None:
    cfg = RateLimitConfig(max_per_second=8.0, burst=16)
    assert cfg.max_per_second == 8.0
    assert cfg.burst == 16
    with pytest.raises(Exception):
        cfg.burst = 1  # type: ignore[misc]


def test_fake_transport_satisfies_protocol() -> None:
    class FakeTransport:
        def __init__(self) -> None:
            self.calls: list[tuple[str, str]] = []

        def get(self, path: str, **kwargs: object) -> dict:
            self.calls.append(("GET", path))
            return {"ok": True, "path": path}

        def post(self, path: str, **kwargs: object) -> dict:
            self.calls.append(("POST", path))
            return {"ok": True, "path": path}

        def put(self, path: str, **kwargs: object) -> dict:
            self.calls.append(("PUT", path))
            return {"ok": True, "path": path}

        def delete(self, path: str, **kwargs: object) -> dict:
            self.calls.append(("DELETE", path))
            return {"ok": True, "path": path}

    transport: BaseTransport = FakeTransport()
    assert transport.get("/quote")["ok"] is True
    assert transport.post("/orders", json={"side": "BUY"})["ok"] is True


def test_broker_adapter_port_surface() -> None:
    required = {
        "connect",
        "authenticate",
        "close",
        "get_quote",
        "place_order",
        "cancel_order",
        "get_positions",
        "get_funds",
        "get_balance",
        "mass_status",
        "capabilities",
    }
    assert required.issubset(set(BrokerAdapterPort.__protocol_attrs__))
