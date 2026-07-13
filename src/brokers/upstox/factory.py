"""UpstoxBrokerFactory — creates configured UpstoxBrokerGateway instances.

Implements BrokerProviderFactory for polymorphic factory pattern.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from typing import Any

from infrastructure.gateway.provider_factory import BrokerProviderFactory
from domain.ports.broker_adapter import BrokerAdapter as MarketDataGateway
from brokers.common.identity.account_registry import AccountConnectionRegistry
from brokers.upstox.auth.config import UpstoxSettingsLoader
from brokers.upstox.auth.exceptions import UpstoxAuthError
from brokers.upstox.broker import UpstoxBroker
from brokers.upstox.wire import UpstoxWireAdapter

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
        if analytics_only or settings.analytics_only:
            settings = replace(settings, analytics_only=True)

        # Reuse one gateway/WebSocket connection per (broker, client_id) per
        # process instead of reconnecting on every bootstrap_gateway() call.
        # Without this, each call built a brand-new UpstoxBroker -> new
        # UpstoxMarketDataV3Multiplexer -> new WS handshake + feed-authorize
        # request, unlike Dhan (which already had this via
        # AccountConnectionRegistry) -- repeated calls in the same process
        # burn connect/authorize cycles and risk provider-side reconnect
        # throttling.
        return AccountConnectionRegistry.get_or_create(
            "upstox",
            settings.client_id,
            lambda: self._build_gateway(
                settings=settings,
                load_instruments=load_instruments,
                event_bus=event_bus,
                risk_manager=risk_manager,
                lifecycle=lifecycle,
                backfill_callback=backfill_callback,
                reconciliation_service=reconciliation_service,
            ),
        )

    def _build_gateway(
        self,
        *,
        settings: Any,
        load_instruments: bool,
        event_bus: Any | None,
        risk_manager: Any | None,
        lifecycle: Any | None,
        backfill_callback: Callable[[list[str], Any, Any], list[dict]] | None,
        reconciliation_service: Any | None,
    ) -> MarketDataGateway:
        broker = UpstoxBroker(
            settings=settings,
            event_bus=event_bus,
            risk_manager=risk_manager,
            backfill_callback=backfill_callback,
            reconciliation_service=reconciliation_service,
        )
        if not broker.connect():
            if settings.is_totp:
                raise UpstoxAuthError(
                    "Upstox TOTP bootstrap failed during connect; "
                    "check credentials, cooldown state, and token persistence"
                )
            logger.warning("Upstox connect failed; gateway created in disconnected state")

        if settings.is_totp and lifecycle is None:
            logger.warning(
                "Upstox TOTP mode without lifecycle manager: daily refresh scheduler "
                "will not run until lifecycle.start_all() wires TotpRefreshScheduler"
            )

        gateway = UpstoxWireAdapter(broker)

        # Register extension factories so brokers.common can find them

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
            from brokers.upstox.websocket.lifecycle_wrapper import (
                UpstoxPortfolioStreamService,
                UpstoxWebSocketService,
            )

            ws_service = UpstoxWebSocketService(
                multiplexer=broker.market_data_websocket,
                name="upstox.websocket",
            )
            portfolio_service = UpstoxPortfolioStreamService(
                stream=broker.portfolio_stream,
                name="upstox.portfolio_stream",
            )
            try:
                lifecycle.register(ws_service)
                lifecycle.register(portfolio_service)
                logger.info(
                    "upstox_websocket_wired",
                    extra={
                        "service": "upstox.websocket",
                        "lifecycle_services": lifecycle.service_names(),
                    },
                )
            except Exception as exc:
                logger.debug("upstox_websocket_register_failed: %s", exc)

            if settings.is_totp:
                from brokers.upstox.auth.totp_scheduler import TotpRefreshScheduler

                scheduler = TotpRefreshScheduler(
                    broker.token_manager,
                    refresh_hour=settings.totp_refresh_hour,
                    refresh_minute=settings.totp_refresh_minute,
                )
                lifecycle.register(scheduler)
                logger.info(
                    "upstox_totp_scheduler_wired",
                    extra={
                        "refresh_time": f"{settings.totp_refresh_hour:02d}:{settings.totp_refresh_minute:02d}",
                    },
                )

        # ── Health check registration ──────────────────────────────
        from infrastructure.observability.health_check import register_broker_health_check

        register_broker_health_check("upstox", gateway)

        return gateway
