"""Broker extension bundle factories for CommonBrokerGateway infrastructure."""

from __future__ import annotations

from brokers.common.extensions import ExtensionBundle
from brokers.common.gateway import MarketDataGateway


def build_extension_bundle(broker_id: str, gateway: MarketDataGateway) -> ExtensionBundle:
    """Build the extension bundle for a registered legacy gateway."""
    if broker_id == "dhan":
        from brokers.dhan.common_extensions import register_dhan_extensions  # noqa: TID251

        return register_dhan_extensions(gateway)
    if broker_id == "upstox":
        from brokers.upstox.common_extensions import register_upstox_extensions  # noqa: TID251

        return register_upstox_extensions(gateway)
    return ExtensionBundle(broker_id)
