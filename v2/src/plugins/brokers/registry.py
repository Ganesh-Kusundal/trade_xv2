"""Broker plugin registry — keyed by BrokerId."""

from __future__ import annotations

from typing import Any

from domain.enums import BrokerId

_PLUGINS: dict[BrokerId, Any] = {}


def register_broker_plugin(broker_id: BrokerId, plugin: Any) -> None:
    _PLUGINS[broker_id] = plugin


def list_plugins() -> list[BrokerId]:
    return list(_PLUGINS)


def get_plugin(broker_id: BrokerId) -> Any:
    return _PLUGINS[broker_id]


def clear_plugins() -> None:
    """ponytail: test isolation only — production never clears mid-session."""
    _PLUGINS.clear()
