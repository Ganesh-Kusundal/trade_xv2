"""BrokerFactory — creates configured DhanBrokerGateway instances with AuthManager.

Implements BrokerProviderFactory for polymorphic factory pattern.
"""

from __future__ import annotations

import logging
import os
import threading
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

from infrastructure.auth import AuthManager, JsonTokenStateStore, TokenSource, TokenState
from tradex.runtime.factory import BrokerProviderFactory
from domain.ports.broker_adapter import BrokerAdapter as MarketDataGateway
from brokers.dhan.identity.account_registry import AccountConnectionRegistry
from brokers.dhan.streaming.connection import DhanConnection
from brokers.dhan.gateway import DhanBrokerGateway
from brokers.dhan.api.http_client import DhanHttpClient
from brokers.dhan.config.settings import DhanConnectionSettings, DhanSettingsLoader
from brokers.dhan.auth.token_scheduler import TokenRefreshScheduler

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

    def _build_gateway(self, *, settings, env_path, load_instruments, event_bus,
                       risk_manager, lifecycle, backfill_callback, reconciliation_service):
        auth = self._create_auth(settings, env_path)
        http_client = self._create_http_client(auth, settings, env_path)
        conn, gateway = self._create_connection_and_gateway(
            settings=settings,
            http_client=http_client,
            load_instruments=load_instruments,
            event_bus=event_bus,
            risk_manager=risk_manager,
            lifecycle=lifecycle,
            backfill_callback=backfill_callback,
            reconciliation_service=reconciliation_service,
        )
        self._wire_websocket_services(conn, gateway, http_client)
        self._setup_token_refresh_scheduler(auth, conn, settings)
        return gateway

    def _create_auth(self, settings: DhanConnectionSettings, env_path: Path) -> AuthManager:
        from datetime import datetime, timedelta
        from infrastructure.auth import AuthManager, JsonTokenStateStore, TokenSource, TokenState

        client_id = settings.client_id
        token = settings.access_token
        
        # Ensure we write token JSON to a JSON file rather than corrupting .env.local
        token_path = settings.resolved_token_state_dir / f"dhan-token-{client_id}.json"
        token_state = JsonTokenStateStore(token_path)
        ttl = settings.token_lifetime_seconds

        def _generate_token() -> str:
            return token

        source = TokenSource.TOTP if settings.totp_secret else TokenSource.STATIC

        if token:
            now = datetime.now()
            expires_at = now + timedelta(seconds=ttl) if ttl else None
            state = TokenState(
                access_token=token,
                issued_at=now,
                expires_at=expires_at,
                source=source,
            )
            token_state.save(state)

        return AuthManager(
            client_id=client_id,
            token_store=token_state,
            token_source=source,
            on_acquire=_generate_token,
            token_lifetime_seconds=ttl,
        )

    def _create_http_client(self, auth: AuthManager, settings: DhanConnectionSettings, env_path: Path) -> DhanHttpClient:
        def _refresh() -> str:
            state = auth.acquire()
            return state.access_token if state else ""

        return DhanHttpClient(
            client_id=settings.client_id,
            access_token=settings.access_token,
            base_url=settings.base_url,
            timeout=settings.http_timeout,
            token_refresh_fn=_refresh,
            enable_retry=settings.enable_retry,
            config=settings.resilience_config,
        )

    def _create_connection_and_gateway(
        self, *, settings, http_client, load_instruments,
        event_bus, risk_manager, lifecycle, backfill_callback, reconciliation_service
    ):
        conn = DhanConnection(
            client=http_client,
            event_bus=event_bus,
            risk_manager=risk_manager,
            backfill_callback=backfill_callback,
            reconciliation_service=reconciliation_service,
            lifecycle=lifecycle,
            allow_live_orders=settings.allow_live_orders,
        )
        if load_instruments:
            conn.load_instruments()
        gateway = DhanBrokerGateway(connection=conn)
        return conn, gateway

    def _wire_websocket_services(self, conn, gateway, http_client):
        conn.create_market_feed()
        conn.create_order_stream()

        def access_token_fn():
            return conn.access_token

        mf = conn.market_feed
        if mf is not None and hasattr(mf, "set_access_token_fn"):
            mf.set_access_token_fn(access_token_fn)

    def _setup_token_refresh_scheduler(self, auth, conn, settings):
        try:
            scheduler = TokenRefreshScheduler(
                auth=auth,
                interval_seconds=settings.scheduler_interval_seconds,
                buffer_seconds=settings.refresh_buffer_seconds,
            )
            scheduler.start()
        except Exception as exc:
            logger.warning("token_refresh_scheduler_failed: %s", exc)


def _refresh_via_auth(auth, conn):
    """Refresh the auth token and propagate to connection."""
    logger.info("token_refresh_triggered")
    try:
        state = auth.state
        if state is None or not state.is_valid():
            new_token = auth.refresh()
            if isinstance(new_token, TokenState):
                new_token = new_token.token
            if new_token and conn:
                conn.access_token = str(new_token)
                logger.info("token_refreshed_and_propagated")
            else:
                logger.warning("token_refresh_empty")
        else:
            logger.info("token_still_valid")
    except Exception as exc:
        logger.error("token_refresh_failed: %s", exc)


def _next_token_expiry(auth) -> datetime | None:
    try:
        state = auth.state
        if state and state.generated_at and state.ttl:
            return state.generated_at + state.ttl
    except Exception:
        pass
    return None


def _generate_totp_token(settings) -> str:
    """Generate TOTP token.
    
    Returns TOTP as a string of digits.
    """
    from brokers.dhan.auth.totp_client import generate_totp as _gt
    return _gt(settings.totp_secret)


def _update_env_token(new_token: str, env_path: Path | None = None) -> bool:
    """Update DHAN_ACCESS_TOKEN in the environment file.
    
    Returns True if update was successful.
    """
    env_file = env_path or Path(".env.local")
    if not env_file.exists():
        logger.warning("env_file_not_found: %s", env_file)
        return False
    try:
        content = env_file.read_text()
        if "DHAN_ACCESS_TOKEN=" in content:
            import re
            content = re.sub(
                r"^DHAN_ACCESS_TOKEN=.*$",
                f"DHAN_ACCESS_TOKEN={new_token}",
                content,
                flags=re.MULTILINE,
            )
        else:
            content += f"\nDHAN_ACCESS_TOKEN={new_token}\n"
        env_file.write_text(content)
        os.environ["DHAN_ACCESS_TOKEN"] = new_token
        logger.info("env_token_updated")
        return True
    except Exception as exc:
        logger.error("env_token_update_failed: %s", exc)
        return False
