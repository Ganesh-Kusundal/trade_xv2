"""Upstox broker adapter — Trade_XV2 implementation.

The full ``UpstoxBroker`` facade lives in :mod:`brokers.providers.upstox.broker` (P12).
This package re-exports it for ``from brokers.providers.upstox import UpstoxBroker``.
"""

from __future__ import annotations

from typing import Any

from .auth.config import UpstoxConnectionSettings, UpstoxSettingsLoader
from .broker import UpstoxBroker as _UpstoxBroker
from .factory import UpstoxBrokerFactory
from .wire import UpstoxWireAdapter


class UpstoxBroker:
    """Upstox broker facade.

    Thin wrapper that instantiates the full :class:`brokers.providers.upstox.broker.UpstoxBroker`
    facade (with all 20+ adapters wired) from the resolved settings.
    """

    def __new__(cls, settings: Any | None = None, **kwargs: Any) -> _UpstoxBroker:
        if settings is None:
            try:
                settings = UpstoxSettingsLoader.from_env()
            except ValueError:
                settings = UpstoxConnectionSettings(client_id="placeholder")
        return _UpstoxBroker(settings=settings, **kwargs)


__all__ = [
    "UpstoxBroker",
    "UpstoxBrokerFactory",
    "UpstoxConnectionSettings",
    "UpstoxSettingsLoader",
    "UpstoxWireAdapter",
]

# ── Extension + execution self-registration (ADR-007) ────────────────────
from brokers.providers.upstox.data_provider import UpstoxDataProvider
from brokers.providers.upstox.extensions.depth import UpstoxDepth30Extension
from brokers.providers.upstox.extensions.news import UpstoxNewsExtension
from infrastructure.adapter_factory import (
    register_broker_extensions,
    register_data_adapter,
    register_execution_provider,
)
from infrastructure.gateway.execution import GatewayExecutionProvider


class UpstoxExecutionProvider(GatewayExecutionProvider):
    """Upstox gateway → domain ExecutionProvider."""

    def __init__(self, gateway: Any) -> None:
        super().__init__(gateway, broker_id="upstox")


register_broker_extensions("upstox", [UpstoxDepth30Extension, UpstoxNewsExtension])
register_data_adapter("upstox", UpstoxDataProvider)
register_execution_provider("upstox", UpstoxExecutionProvider)

from infrastructure.broker_plugin import BrokerPlugin, register_broker_plugin


def _load_upstox_capabilities():
    from brokers.providers.upstox.capabilities.snapshot import upstox_capabilities

    return upstox_capabilities()


register_broker_plugin(
    BrokerPlugin(
        broker_id="upstox",
        env_file=".env.upstox",
        default_mode="market",
        supported_modes=frozenset({"market", "trade"}),
        is_live=True,
        capabilities_loader=_load_upstox_capabilities,
    )
)

from brokers.providers.upstox.instruments.segment_mapper import UpstoxSegmentMapper
from domain.market.segment_registry import register_segment_mapper

register_segment_mapper("upstox", UpstoxSegmentMapper)
