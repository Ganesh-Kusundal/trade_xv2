"""BrokerFactory — creates configured BrokerGateway instances with AuthManager.

Implements BrokerProviderFactory for polymorphic factory pattern.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any

from brokers.common.auth import AuthManager, JsonTokenStateStore, TokenSource
from brokers.common.auth.token_persistence import TokenPersistence, token_state_from_access_token
from brokers.common.auth.token_policy import should_generate_token
from brokers.common.factory import BrokerProviderFactory
from brokers.common.gateway import MarketDataGateway
from brokers.dhan.connection import DhanConnection
from brokers.dhan.gateway import BrokerGateway
from brokers.dhan.http_client import DhanHttpClient
from brokers.dhan.settings import DhanConnectionSettings, DhanSettingsLoader
from brokers.dhan.token_manager import update_env_token
from brokers.dhan.token_scheduler import TokenRefreshScheduler
from brokers.dhan.totp_client import DhanTotpClient

logger = logging.getLogger(__name__)


class BrokerFactory(BrokerProviderFactory):
    def create(
        self,
        *,
        env_path: Path | None = None,
        load_instruments: bool = True,
        event_bus: Any | None = None,
        risk_manager: Any | None = None,
        lifecycle: Any | None = None,
        backfill_callback: Callable[[str, datetime, datetime], list[dict]] | None = None,
        reconciliation_service: object | None = None,
    ) -> MarketDataGateway:
        settings = DhanSettingsLoader.from_env(env_path=env_path)
        cid = settings.client_id
        env_file = env_path or Path(".env.local")

        auth, token = self._create_auth(settings, env_file)

        refresh_lock = threading.Lock()
        client = self._create_http_client(settings, auth, cid, token, env_file, refresh_lock)

        gateway = self._create_connection_and_gateway(
            client, auth, settings, event_bus, risk_manager, reconciliation_service,
            backfill_callback, lifecycle,
        )

        if load_instruments:
            gateway.load_instruments()

        self._wire_websocket_services(gateway, client, token, lifecycle, event_bus)
        self._setup_token_refresh_scheduler(
            gateway, auth, client, settings, env_file, lifecycle, refresh_lock,
        )

        return gateway

    def _create_auth(
        self,
        settings: DhanConnectionSettings,
        env_file: Path,
    ) -> tuple[AuthManager, str]:
        """Create AuthManager and acquire an access token without redundant TOTP."""
        cid = settings.client_id
        token_state_dir = Path("runtime")
        token_state_dir.mkdir(parents=True, exist_ok=True)
        token_store = JsonTokenStateStore(token_state_dir / "dhan-token-state.json")
        totp_client = DhanTotpClient(settings)

        def _generate_token() -> str | None:
            return totp_client.generate()

        auth = AuthManager(
            client_id=cid,
            token_store=token_store,
            token_source=TokenSource.TOTP,
            on_acquire=_generate_token,
            on_refresh=_generate_token,
            token_lifetime_seconds=settings.token_lifetime_seconds,
        )

        now = datetime.now()
        fallback_expiry = _next_token_expiry(now, settings.token_lifetime_seconds)
        state = TokenPersistence.load_canonical(
            token_store,
            settings.access_token,
            fallback_expires_at=fallback_expiry,
        )

        if state and state.is_valid() and not should_generate_token(state):
            auth._state = state
            token = state.access_token
            logger.debug("dhan_auth: reusing valid persisted token")
        elif should_generate_token(state):
            fresh = totp_client.generate()
            if not fresh:
                from brokers.dhan.exceptions import ConfigurationError

                raise ConfigurationError(
                    "DHAN_ACCESS_TOKEN not configured and TOTP refresh failed"
                )
            state = token_state_from_access_token(
                fresh,
                source=TokenSource.TOTP,
                fallback_expires_at=fallback_expiry,
            )
            auth._state = state
            TokenPersistence.save(state, token_store, env_file)
            token = fresh
            logger.info("dhan_auth: generated new TOTP token")
        else:
            from brokers.dhan.exceptions import ConfigurationError

            raise ConfigurationError("DHAN_ACCESS_TOKEN not configured and no valid token in store")

        return auth, token

    def _create_http_client(
        self,
        settings: DhanConnectionSettings,
        auth: AuthManager,
        cid: str,
        token: str,
        env_file: Path,
        refresh_lock: threading.Lock,
    ) -> DhanHttpClient:
        from brokers.common.resilience.circuit_breaker import CircuitBreaker, CircuitBreakerConfig

        cb_read = CircuitBreaker(
            "dhan-read-cb",
            CircuitBreakerConfig(failure_threshold=10, open_duration_ms=15_000),
        )
        cb_write = CircuitBreaker(
            "dhan-write-cb",
            CircuitBreakerConfig(failure_threshold=3, open_duration_ms=30_000),
        )
        cb_admin = CircuitBreaker(
            "dhan-admin-cb",
            CircuitBreakerConfig(failure_threshold=5, open_duration_ms=30_000),
        )

        return DhanHttpClient(
            client_id=cid,
            access_token=token,
            base_url=settings.base_url,
            timeout=settings.http_timeout,
            enable_retry=settings.enable_retry,
            token_refresh_fn=lambda: _refresh_via_auth(auth, env_file, refresh_lock, token_store_path=Path("runtime/dhan-token-state.json")),
            read_circuit_breaker=cb_read,
            write_circuit_breaker=cb_write,
            admin_circuit_breaker=cb_admin,
        )

    def _create_connection_and_gateway(
        self,
        client: DhanHttpClient,
        auth: AuthManager,
        settings: DhanConnectionSettings,
        event_bus: Any | None,
        risk_manager: Any | None,
        reconciliation_service: object | None,
        backfill_callback: Callable[[str, datetime, datetime], list[dict]] | None,
        lifecycle: Any | None,
    ) -> BrokerGateway:
        connection = DhanConnection(
            client=client,
            event_bus=event_bus,
            risk_manager=risk_manager,
            backfill_callback=backfill_callback,
            reconciliation_service=reconciliation_service,
            lifecycle=lifecycle,
            allow_live_orders=settings.allow_live_orders,
        )
        connection._auth = auth
        return BrokerGateway(connection)

    def _wire_websocket_services(
        self,
        gateway: BrokerGateway,
        client: DhanHttpClient,
        token: str,
        lifecycle: Any | None,
        event_bus: Any | None,
    ) -> None:
        if lifecycle is None or event_bus is None:
            return

        def access_token_fn():
            return client.access_token

        gateway._conn.create_market_feed(
            access_token=token,
            instruments=[],
            access_token_fn=access_token_fn,
        )
        gateway._conn.create_order_stream(
            access_token=token,
            access_token_fn=access_token_fn,
        )

        logger.info("websocket_wired", extra={
            "market_feed": "dhan.market_feed",
            "order_stream": "dhan.order_stream",
            "depth_20": "on_demand",
            "depth_200": "on_demand",
        })

    def _setup_token_refresh_scheduler(
        self,
        gateway: BrokerGateway,
        auth: AuthManager,
        client: DhanHttpClient,
        settings: DhanConnectionSettings,
        env_file: Path,
        lifecycle: Any | None,
        refresh_lock: threading.Lock,
    ) -> None:
        token_store = JsonTokenStateStore(Path("runtime/dhan-token-state.json"))

        def _on_token_refresh(new_token: str) -> None:
            client.update_token(new_token)
            update_env_token(env_file, new_token)
            delivered = gateway._conn.broadcast_token(new_token)
            logger.info(
                "dhan_token_refreshed",
                extra={
                    "token_suffix": new_token[-6:] if new_token else "",
                    "receivers": delivered,
                },
            )

        scheduler = TokenRefreshScheduler(
            auth=auth,
            interval_seconds=settings.scheduler_interval_seconds,
            buffer_seconds=settings.refresh_buffer_seconds,
            refresh_lock=refresh_lock,
            on_refresh=_on_token_refresh,
            token_store=token_store,
            env_file=env_file,
        )
        if lifecycle is not None:
            lifecycle.register(scheduler)
            gateway._conn._token_scheduler = scheduler
        else:
            scheduler.start()
            gateway._conn._token_scheduler = scheduler


def _refresh_via_auth(
    auth: AuthManager,
    env_file: Path,
    refresh_lock: threading.Lock,
    *,
    token_store_path: Path | None = None,
) -> str | None:
    """Refresh token via AuthManager when broker rejects the current token."""
    acquired = refresh_lock.acquire(timeout=5.0)
    if not acquired:
        logger.debug("Token refresh timed out waiting for in-flight refresh")
        return None
    try:
        state = auth.force_refresh()
        if state and state.access_token:
            store = JsonTokenStateStore(token_store_path or Path("runtime/dhan-token-state.json"))
            TokenPersistence.save(state, store, env_file)
            return state.access_token
        return None
    finally:
        refresh_lock.release()


def _next_token_expiry(now: Any, lifetime_seconds: int) -> Any:
    """Compute token expiry aligned to the next trading session end."""
    from datetime import timedelta, timezone

    try:
        if now.tzinfo is None:
            utc_now = datetime.now(timezone.utc)
        else:
            utc_now = now.astimezone(timezone.utc)
        session_end_today = utc_now.replace(hour=0, minute=30, second=0, microsecond=0)
        if utc_now < session_end_today:
            expiry = session_end_today
        else:
            expiry = session_end_today + timedelta(days=1)
        return expiry.replace(tzinfo=None)
    except Exception:
        base = now.replace(tzinfo=None) if getattr(now, "tzinfo", None) else now
        return base + timedelta(seconds=lifetime_seconds)


# Backward-compatible re-exports for tests and authenticated_readiness
from brokers.dhan.token_manager import update_env_token as _update_env_token  # noqa: E402

__all__ = ["BrokerFactory", "_update_env_token", "_next_token_expiry", "_refresh_via_auth"]
