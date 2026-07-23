"""Upstox broker plugin — sandbox-capable gateway with injectable transport."""

from __future__ import annotations

from domain.enums import BrokerId
from plugins.brokers.registry import register_broker_plugin
from plugins.brokers.upstox.gateway import UPSTOX_CAPABILITIES, UpstoxGateway

__all__ = ["UPSTOX_CAPABILITIES", "UpstoxGateway", "register"]


def register() -> BrokerId:
    register_broker_plugin(
        BrokerId.UPSTOX,
        {"gateway": UpstoxGateway, "capabilities": UPSTOX_CAPABILITIES},
    )
    return BrokerId.UPSTOX
