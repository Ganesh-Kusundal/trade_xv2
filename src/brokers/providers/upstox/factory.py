"""UpstoxBrokerFactory — creates configured UpstoxWireAdapter instances.

Implements BrokerProviderFactory for polymorphic factory pattern.
"""

from __future__ import annotations

import atexit
import logging
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from typing import Any

from brokers.common.identity.account_registry import AccountConnectionRegistry
from brokers.providers.upstox.auth.config import UpstoxSettingsLoader
from brokers.providers.upstox.auth.exceptions import UpstoxAuthError
from brokers.providers.upstox.broker import UpstoxBroker
from brokers.providers.upstox.wire import UpstoxWireAdapter
from domain.ports.broker_adapter import BrokerAdapter
from infrastructure.gateway.provider_factory import BrokerProviderFactory

logger = logging.getLogger(__name__)

# One TOTP refresh scheduler per token manager for the process lifetime.
# Reusing the scheduler avoids spawning a new daemon thread + atexit handler on
# every UpstoxBrokerFactory.create() call (the gateway itself is already
# de-duplicated via AccountConnectionRegistry).
_active_totp_schedulers: dict[int, Any] = {}


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
    ) -> BrokerAdapter:
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
    ) -> BrokerAdapter:
        broker = UpstoxBroker(
            settings=settings,
            event_bus=event_bus,
            risk_manager=risk_manager,
            backfill_callback=backfill_callback,
            reconciliation_service=reconciliation_service,
        )
        connect_ok = broker.connect()
        if not connect_ok:
            if settings.is_totp:
                raise UpstoxAuthError(
                    "Upstox TOTP bootstrap failed during connect; "
                    "check credentials, cooldown state, and token persistence"
                )
            logger.warning("Upstox connect failed; gateway created in disconnected state")

        if settings.is_totp and lifecycle is None:
            from brokers.providers.upstox.auth.totp_scheduler import TotpRefreshScheduler

            tm = broker.token_manager
            scheduler = _active_totp_schedulers.get(id(tm))
            if scheduler is None:
                scheduler = TotpRefreshScheduler(
                    tm,
                    refresh_hour=settings.totp_refresh_hour,
                    refresh_minute=settings.totp_refresh_minute,
                )
                scheduler.start()
                atexit.register(scheduler.stop)
                _active_totp_schedulers[id(tm)] = scheduler
            logger.warning(
                "upstox_totp_scheduler_started_without_lifecycle",
                extra={"hint": "registered atexit stop handler"},
            )

        gateway = UpstoxWireAdapter(broker)
        gateway.bootstrap_transport_ready = connect_ok

        # Register extension factories so brokers.common can find them

        if load_instruments:
            try:
                gateway.load_instruments()
            except Exception as e:
                # ponytail: instrument load is best-effort for analytics; live
                # sessions with require_authenticated=True still fail the auth probe.
                logger.warning("Failed to load Upstox instruments: %s", e)
                if not settings.analytics_only and settings.is_totp:
                    raise

        # ── Auto-wire WebSocket lifecycle ──────────────────────────────
        # When lifecycle is provided, register the WebSocket multiplexer
        # as a ManagedService so it participates in deterministic
        # start/stop. This mirrors the Dhan factory pattern.
        if lifecycle is not None:
            from brokers.providers.upstox.websocket.lifecycle_wrapper import (
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
                from brokers.providers.upstox.auth.totp_scheduler import TotpRefreshScheduler

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
