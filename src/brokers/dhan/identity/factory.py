"""BrokerFactory — creates configured DhanWireAdapter instances with AuthManager.

Implements BrokerProviderFactory for polymorphic factory pattern.

Auth policy (probe-before-mint)
-------------------------------
* Reuse env/store JWT when still locally valid — never burn TOTP.
* On missing/expired token at bootstrap: mint once via ``DhanTotpClient``.
* On broker 401/DH-906: ``force_refresh`` (``on_refresh``) mints once and
  propagates via HTTP client + connection broadcast.
* ``AuthManager`` is stored on ``connection._auth`` so
  ``authenticated_readiness_probe`` can remint after rejection.
"""

from __future__ import annotations

import atexit
import logging
import os
import threading
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any

from brokers.dhan.api.http_client import DhanHttpClient
from brokers.dhan.config.settings import DhanConnectionSettings, DhanSettingsLoader
from brokers.dhan.identity.account_registry import AccountConnectionRegistry
from brokers.dhan.streaming.connection import DhanConnection
from brokers.dhan.streaming.session_manager import DhanSessionManager
from brokers.dhan.wire import DhanWireAdapter
from domain.ports.broker_adapter import BrokerAdapter as MarketDataGateway
from infrastructure.auth import AuthManager, JsonTokenStateStore, TokenSource
from infrastructure.auth.env_token import update_env_token as _infra_update_env_token
from infrastructure.auth.token_ensure import ensure_access_token
from infrastructure.auth.token_persistence import TokenPersistence
from infrastructure.gateway.provider_factory import BrokerProviderFactory

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
        resolved_env = env_path or Path(".env.local")

        return AccountConnectionRegistry.get_or_create(
            "dhan",
            cid,
            lambda: self._build_gateway(
                settings=settings,
                env_path=resolved_env,
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
        settings: DhanConnectionSettings,
        env_path: Path,
        load_instruments: bool,
        event_bus: Any | None,
        risk_manager: Any | None,
        lifecycle: Any | None,
        backfill_callback: Callable[[str, datetime, datetime], list[dict]] | None,
        reconciliation_service: object | None,
    ) -> MarketDataGateway:
        # ── Auth & token ───────────────────────────────────────────
        auth, token = self._create_auth(settings, env_path)

        # Shared lock for HTTP 401 remint + scheduler.
        refresh_lock = threading.Lock()

        # ── HTTP client ────────────────────────────────────────────
        client = self._create_http_client(settings, auth, token, env_path, refresh_lock)

        # ── Connection + Gateway ───────────────────────────────────
        gateway = self._create_connection_and_gateway(
            client,
            auth,
            settings,
            event_bus,
            risk_manager,
            reconciliation_service,
            backfill_callback,
            lifecycle,
        )

        if load_instruments:
            gateway.load_instruments()

        # ── WebSocket auto-wiring ──────────────────────────────────
        self._wire_websocket_services(gateway, client, token, lifecycle, event_bus)

        # ── Token refresh scheduler ────────────────────────────────
        self._setup_token_refresh_scheduler(
            gateway,
            auth,
            client,
            settings,
            env_path,
            lifecycle,
            refresh_lock,
        )

        return gateway

    # ── Bootstrapper helpers ──────────────────────────────────────────────

    def _create_auth(
        self,
        settings: DhanConnectionSettings,
        env_file: Path,
    ) -> tuple[AuthManager, str]:
        """Create AuthManager and resolve an access token (probe-before-mint).

        Policy (token_ensure):
        * Reuse env/store JWT when still valid — never TOTP.
        * Mint at most once via ``DhanTotpClient`` (TotpCooldownGuard).
        * Persist store + env atomically on mint.
        """
        cid = settings.client_id
        token_state_dir = settings.resolved_token_state_dir
        token_state_dir.mkdir(parents=True, exist_ok=True)
        # Canonical store name (shared with readiness probe persistence).
        token_store = JsonTokenStateStore(token_state_dir / "dhan-token-state.json")

        def _generate_token() -> str | None:
            # Call module-local mint so tests can patch
            # ``brokers.dhan.identity.factory._generate_totp_token``.
            return _generate_totp_token(settings)

        auth = AuthManager(
            client_id=cid,
            token_store=token_store,
            token_source=TokenSource.TOTP if settings.has_totp else TokenSource.STATIC,
            on_acquire=_generate_token,
            on_refresh=_generate_token,  # force_refresh on 401 uses this
            token_lifetime_seconds=settings.token_lifetime_seconds,
        )

        try:
            state = ensure_access_token(
                store=token_store,
                env_token=settings.access_token or None,
                mint=_generate_token,
                env_path=env_file if env_file.exists() else None,
                env_key="DHAN_ACCESS_TOKEN",
                broker_rejected=False,
                allow_proactive=False,  # never burn TOTP for proactive refresh
                source=TokenSource.TOTP if settings.has_totp else TokenSource.STATIC,
            )
        except Exception as exc:
            from brokers.dhan.exceptions import ConfigurationError

            raise ConfigurationError(
                f"DHAN_ACCESS_TOKEN not configured and TOTP refresh failed: {exc}"
            ) from exc

        if not state or not state.access_token:
            from brokers.dhan.exceptions import ConfigurationError

            raise ConfigurationError("DHAN_ACCESS_TOKEN not configured and TOTP refresh failed")

        # Hydrate AuthManager so 401 refresh / scheduler share the same state.
        auth._set_token(state.access_token, source=state.source)
        return auth, state.access_token

    def _create_http_client(
        self,
        settings: DhanConnectionSettings,
        auth: AuthManager,
        token: str,
        env_file: Path,
        refresh_lock: threading.Lock,
    ) -> DhanHttpClient:
        """Create DhanHttpClient with 401 → force_refresh remint."""
        return DhanHttpClient(
            client_id=settings.client_id,
            access_token=token,
            base_url=settings.base_url,
            timeout=settings.http_timeout,
            enable_retry=settings.enable_retry,
            token_refresh_fn=lambda: _refresh_via_auth(auth, env_file, refresh_lock),
            config=settings.resilience_config,
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
    ) -> DhanWireAdapter:
        """Create DhanConnection + DhanWireAdapter (transport facade)."""
        connection = DhanConnection(
            client=client,
            event_bus=event_bus,
            risk_manager=risk_manager,
            backfill_callback=backfill_callback,
            reconciliation_service=reconciliation_service,
            lifecycle=lifecycle,
            allow_live_orders=settings.allow_live_orders,
        )
        # Required by authenticated_readiness._force_dhan_token_refresh
        connection._auth = auth
        connection._session_manager = DhanSessionManager(connection, auth)
        return DhanWireAdapter(connection)

    def _wire_websocket_services(
        self,
        gateway: DhanWireAdapter,
        client: DhanHttpClient,
        token: str,
        lifecycle: Any | None,
        event_bus: Any | None,
    ) -> None:
        """Auto-create and register WebSocket services when lifecycle is provided."""
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

        logger.info(
            "websocket_wired",
            extra={
                "market_feed": "dhan.market_feed",
                "order_stream": "dhan.order_stream",
                "depth_20": "on_demand",
                "depth_200": "on_demand",
            },
        )

    def _setup_token_refresh_scheduler(
        self,
        gateway: DhanWireAdapter,
        auth: AuthManager,
        client: DhanHttpClient,
        settings: DhanConnectionSettings,
        env_file: Path,
        lifecycle: Any | None,
        refresh_lock: threading.Lock,
    ) -> None:
        """Create and register the token refresh scheduler."""

        def _on_token_refresh(new_token: str) -> None:
            client.update_token(new_token)
            if env_file.exists():
                _update_env_token(env_file, new_token)
            delivered = gateway._conn.broadcast_token(new_token)
            logger.info(
                "dhan_token_refreshed",
                extra={
                    "token_suffix": new_token[-6:] if new_token else "",
                    "receivers": delivered,
                },
            )

        from brokers.dhan.auth.token_scheduler import TokenRefreshScheduler

        scheduler = TokenRefreshScheduler(
            auth=auth,
            interval_seconds=settings.scheduler_interval_seconds,
            buffer_seconds=settings.refresh_buffer_seconds,
            refresh_lock=refresh_lock,
            on_refresh=_on_token_refresh,
            token_store=getattr(auth, "_store", None),
            env_file=env_file if env_file.exists() else None,
        )
        if lifecycle is not None:
            lifecycle.register(scheduler)
            gateway._conn.token_scheduler = scheduler
        else:
            scheduler.start()
            gateway._conn.token_scheduler = scheduler
            atexit.register(scheduler.stop)
            logger.warning(
                "token_scheduler_started_without_lifecycle",
                extra={"hint": "registered atexit stop handler"},
            )


def _refresh_via_auth(
    auth: AuthManager,
    env_file: Path,
    refresh_lock: threading.Lock,
) -> str | None:
    """Refresh after broker rejection (401/DH-906) — single mint, no store reload.

    Clears AuthManager state first so we never re-serve a rejected JWT from
    disk. Does **not** call ``acquire()`` after a failed force_refresh (that
    previously reloaded the same stale store token).
    """
    acquired = refresh_lock.acquire(timeout=5.0)
    if not acquired:
        logger.debug("Token refresh timed out waiting for in-flight refresh")
        return None
    try:
        # Drop rejected token from memory + store so acquire cannot revive it.
        auth.revoke()
        state = auth.force_refresh()
        if state and state.access_token:
            if auth._store is not None:
                TokenPersistence.save(
                    state,
                    auth._store,
                    env_file if env_file.exists() else None,
                    env_key="DHAN_ACCESS_TOKEN",
                )
            else:
                _update_env_token(env_file, state.access_token)
            return state.access_token
        return None
    finally:
        refresh_lock.release()


def _generate_totp_token(settings: DhanConnectionSettings | None = None) -> str | None:
    """Generate a fresh access token via TOTP (single path through TotpCooldownGuard).

    Delegates to :class:`DhanTotpClient` so factory, HTTP 401 refresh, and
    ad-hoc diagnostics share the same cooldown and broker rate-limit handling.

    Raises ``TotpRateLimitError`` so callers can surface cooldown distinctly.
    Returns ``None`` on other mint failures (invalid TOTP, network, etc.).
    """
    # Import via package shim so unit tests can patch
    # ``brokers.dhan.auth.totp_client.DhanTotpClient``.
    from brokers.dhan.auth.totp_client import DhanTotpClient
    from infrastructure.auth.totp_cooldown import TotpRateLimitError

    try:
        token = DhanTotpClient(settings).generate()
    except TotpRateLimitError:
        raise
    except Exception as exc:
        logger.warning("TOTP token generation failed: %s", exc)
        return None
    if not token:
        # Surface empty mint so AuthManager logs a clear failure reason.
        logger.warning("TOTP token generation returned empty (invalid TOTP or API error)")
    return token


def _update_env_token(env_path: Path, token: str) -> None:
    """Update DHAN_ACCESS_TOKEN in the env file atomically."""
    _infra_update_env_token(env_path, token, env_key="DHAN_ACCESS_TOKEN")
    os.environ["DHAN_ACCESS_TOKEN"] = token
