"""Upstox broker plugin — sandbox-capable gateway with injectable transport."""

from __future__ import annotations

from domain.enums import BrokerId
from plugins.brokers.registry import register_broker_plugin
from plugins.brokers.upstox.gateway import UpstoxGateway

__all__ = ["UpstoxGateway", "register"]


def register() -> BrokerId:
    register_broker_plugin(BrokerId.UPSTOX, UpstoxGateway)
    return BrokerId.UPSTOX
