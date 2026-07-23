"""Dhan broker plugin — sandbox-capable gateway with injectable transport."""

from __future__ import annotations

from domain.enums import BrokerId
from plugins.brokers.dhan.gateway import DHAN_CAPABILITIES, DhanGateway
from plugins.brokers.registry import register_broker_plugin

__all__ = ["DHAN_CAPABILITIES", "DhanGateway", "register"]


def register() -> BrokerId:
    register_broker_plugin(
        BrokerId.DHAN,
        {"gateway": DhanGateway, "capabilities": DHAN_CAPABILITIES},
    )
    return BrokerId.DHAN
