"""Dhan broker plugin — sandbox-capable gateway with injectable transport."""

from __future__ import annotations

from domain.enums import BrokerId
from plugins.brokers.dhan.gateway import DhanGateway
from plugins.brokers.registry import register_broker_plugin

__all__ = ["DhanGateway", "register"]


def register() -> BrokerId:
    register_broker_plugin(BrokerId.DHAN, DhanGateway)
    return BrokerId.DHAN
