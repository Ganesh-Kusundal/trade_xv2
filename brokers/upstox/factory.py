"""UpstoxBrokerFactory — creates configured UpstoxBrokerGateway instances.

Implements BrokerProviderFactory for polymorphic factory pattern.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Callable
from pathlib import Path
from typing import Any

from brokers.common.env_loader import load_env_file
from brokers.common.event_bus import EventBus
from brokers.common.factory import BrokerProviderFactory
from brokers.common.gateway import MarketDataGateway
from brokers.common.oms.risk_manager import RiskManager
from brokers.upstox.auth.config import UpstoxConnectionSettings, UpstoxSettingsLoader
from brokers.upstox.broker import UpstoxBroker
from brokers.upstox.gateway import UpstoxBrokerGateway

logger = logging.getLogger(__name__)


class UpstoxBrokerFactory(BrokerProviderFactory):
    def create(
        self,
        *,
        env_path: Path | None = None,
        load_instruments: bool = True,
        event_bus: Any | None = None,
        risk_manager: Any | None = None,
        lifecycle: Any | None = None,
        analytics_only: bool = False,
        backfill_callback: Callable[[list[str], Any, Any], list[dict]] | None = None,
        reconciliation_service: Any | None = None,
    ) -> MarketDataGateway:
        # Use the canonical settings loader instead of manual env reads.
        settings = UpstoxSettingsLoader.from_env(env_path=env_path)
        analytics_only = analytics_only or settings.analytics_only

        broker = UpstoxBroker(
            settings=settings,
            event_bus=event_bus,
            risk_manager=risk_manager,
            backfill_callback=backfill_callback,
            reconciliation_service=reconciliation_service,
        )
        broker.connect()

        gateway = UpstoxBrokerGateway(broker)

        if load_instruments:
            try:
                gateway.load_instruments()
            except Exception as e:
                logger.warning("Failed to load Upstox instruments: %s", e)

        # ── Auto-wire WebSocket lifecycle ──────────────────────────────
        # When lifecycle is provided, register the WebSocket multiplexer
        # as a ManagedService so it participates in deterministic
        # start/stop. This mirrors the Dhan factory pattern.
        if lifecycle is not None:
            from brokers.upstox.websocket.lifecycle_wrapper import UpstoxWebSocketService
            ws_service = UpstoxWebSocketService(
                multiplexer=broker.market_data_websocket,
                name="upstox.websocket",
            )
            try:
                lifecycle.register(ws_service)
                logger.info("upstox_websocket_wired", extra={
                    "service": "upstox.websocket",
                    "lifecycle_services": lifecycle.service_names(),
                })
            except Exception as exc:
                logger.debug("upstox_websocket_register_failed: %s", exc)

        return gateway


