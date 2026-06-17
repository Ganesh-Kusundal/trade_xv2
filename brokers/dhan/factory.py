"""BrokerFactory — creates configured BrokerGateway instances with AuthManager.

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

from brokers.common.core.auth import AuthManager, JsonTokenStateStore, TokenSource, TokenState
from brokers.common.env_loader import load_env_file
from brokers.common.factory import BrokerProviderFactory
from brokers.common.gateway import MarketDataGateway
from brokers.dhan.connection import DhanConnection
from brokers.dhan.gateway import BrokerGateway
from brokers.dhan.http_client import DhanHttpClient
from brokers.dhan.settings import DhanConnectionSettings, DhanSettingsLoader
from brokers.dhan.token_scheduler import TokenRefreshScheduler

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
        # ── Load settings ──────────────────────────────────────────
        settings = DhanSettingsLoader.from_env(env_path=env_path)
        cid = settings.client_id

        # ── AuthManager setup ──────────────────────────────────────
        token_state_dir = Path("runtime")
        token_state_dir.mkdir(parents=True, exist_ok=True)
        token_store = JsonTokenStateStore(token_state_dir / "dhan-token-state.json")

        # Build the TOTP token generator closure
        def _generate_token() -> str | None:
            return _generate_totp_token(settings)

        auth = AuthManager(
            client_id=cid,
            token_store=token_store,
            token_source=TokenSource.TOTP,
            on_acquire=_generate_token,
            on_refresh=_generate_token,
            token_lifetime_seconds=settings.token_lifetime_seconds,
        )

        # ── Token acquisition ──────────────────────────────────────
        env_file = env_path or Path(".env.local")
        token = settings.access_token
        if not token:
            # Try store first, then generate fresh token
            state = auth.acquire()
            if not state or not state.is_valid():
                # Store was empty/expired — generate fresh token directly
                fresh = _generate_totp_token(settings)
                if fresh:
                    from datetime import datetime, timedelta
                    state = TokenState(
                        access_token=fresh,
                        source=TokenSource.TOTP,
                        issued_at=datetime.now(),
                        expires_at=datetime.now() + timedelta(seconds=settings.token_lifetime_seconds),
                    )
                    auth._state = state
                    if auth._store:
                        auth._store.save(state)
                else:
                    state = None

            if not state or not state.access_token:
                from brokers.dhan.exceptions import ConfigurationError
                raise ConfigurationError("DHAN_ACCESS_TOKEN not configured and TOTP refresh failed")

            token = state.access_token

            # Also update .env.local for backward compatibility
            if env_file.exists():
                _update_env_token(env_file, token)

        # ── HTTP client ────────────────────────────────────────────
        from brokers.common.resilience.circuit_breaker import CircuitBreaker, CircuitBreakerConfig

        # Three independent circuit breakers — one per endpoint category.
        # Phase A / A1 split the previous single "dhan-api" breaker so a
        # failure storm on read endpoints (e.g. option-chain during a
        # volatile session) cannot OPEN the breaker for write endpoints
        # (order placement). This is the same failure mode that caused
        # the documented DH-906 incident, generalised: any category's
        # outage previously took out the others. See
        # PRODUCTION_CERTIFICATION_REPORT §B1.
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

        # Per-instance refresh lock shared between the HTTP 401 handler
        # and the scheduler. This replaces the previous module-level
        # `_token_refresh_lock` global, which leaked across every
        # gateway constructed in the process.
        refresh_lock = threading.Lock()

        client = DhanHttpClient(
            client_id=cid,
            access_token=token,
            base_url=settings.base_url,
            timeout=settings.http_timeout,
            enable_retry=settings.enable_retry,
            token_refresh_fn=lambda: _refresh_via_auth(auth, env_file, refresh_lock),
            read_circuit_breaker=cb_read,
            write_circuit_breaker=cb_write,
            admin_circuit_breaker=cb_admin,
        )

        # ── Connection + Gateway ───────────────────────────────────
        connection = DhanConnection(
            client=client,
            event_bus=event_bus,
            # B7: thread the OMS's risk_manager so the OrdersAdapter
            # consults it on every place_order call. The OMS is the
            # canonical owner of risk checks; OrdersAdapter is a
            # transport-layer executor.
            risk_manager=risk_manager,
            backfill_callback=backfill_callback,
            reconciliation_service=reconciliation_service,
            # B5: thread the lifecycle so lazily-created WebSocket
            # services (DhanMarketFeed, DhanOrderStream,
            # PollingMarketFeed) are registered with it.
            lifecycle=lifecycle,
        )
        connection._auth = auth  # Store auth manager on connection
        gateway = BrokerGateway(connection)

        if load_instruments:
            gateway.load_instruments()

        # ── Auto-wire WebSocket services ─────────────────────────────
        # When both lifecycle and event_bus are provided, auto-create
        # and register WebSocket services so they're managed by the
        # lifecycle. This fixes the readiness check failure:
        # "websocket_market_feed_wired — DhanMarketFeed was not created"
        if lifecycle is not None and event_bus is not None:
            # Create and register market feed
            def access_token_fn():
                return client.access_token
            connection.create_market_feed(
                access_token=token,
                instruments=[],  # Empty — subscribe on-demand via gateway.stream()
                access_token_fn=access_token_fn,
            )

            # Create and register order stream
            connection.create_order_stream(
                access_token=token,
                access_token_fn=access_token_fn,
            )

            # Note: Depth 20/200 feeds are created on-demand via gateway.depth_20/depth_200
            # since they require specific instrument subscriptions.
            # They will be auto-registered with lifecycle when created.

            logger.info("websocket_wired", extra={
                "market_feed": "dhan.market_feed",
                "order_stream": "dhan.order_stream",
                "depth_20": "on_demand",
                "depth_200": "on_demand",
            })

        # ── Token refresh scheduler ────────────────────────────────
        def _on_token_refresh(new_token: str) -> None:
            """Push fresh token to HTTP client and WebSocket."""
            client.update_token(new_token)
            if env_file.exists():
                _update_env_token(env_file, new_token)
            # Update WebSocket if connected
            feed = connection._market_feed
            if feed is not None:
                feed.update_token(new_token)

        scheduler = TokenRefreshScheduler(
            auth=auth,
            interval_seconds=settings.scheduler_interval_seconds,
            buffer_seconds=settings.refresh_buffer_seconds,
            refresh_lock=refresh_lock,
            on_refresh=_on_token_refresh,
        )
        if lifecycle is not None:
            # New path: the caller owns the lifecycle and the scheduler
            # is just one of many managed services. The factory does
            # not start it directly.
            lifecycle.register(scheduler)
            connection._token_scheduler = scheduler
        else:
            # Backward-compatible path: auto-start the scheduler. This
            # path is the same one the CLI takes and keeps the daemon
            # leak that Wave 2 is closing. New callers should always
            # pass `lifecycle`.
            scheduler.start()
            connection._token_scheduler = scheduler

        return gateway


def _refresh_via_auth(
    auth: AuthManager,
    env_file: Path,
    refresh_lock: threading.Lock,
) -> str | None:
    """Refresh token via AuthManager and persist to .env.local.

    Uses the lock shared with the scheduler to prevent concurrent
    refresh from the HTTP 401 handler and the background scheduler.
    """
    if not refresh_lock.acquire(blocking=False):
        # Another refresh is already in progress
        logger.debug("Token refresh already in progress, skipping")
        return None
    try:
        state = auth.acquire()
        if state and state.access_token:
            _update_env_token(env_file, state.access_token)
            return state.access_token
        return None
    finally:
        refresh_lock.release()


def _generate_totp_token(settings: DhanConnectionSettings | None = None) -> str | None:
    """Generate a fresh access token via TOTP. Returns None on failure.

    Uses secrets from *settings* if provided, otherwise falls back to
    environment variables ``DHAN_PIN`` / ``DHAN_TOTP_SECRET``.
    """
    if settings and settings.has_totp:
        pin = settings.pin
        totp_secret = settings.totp_secret
        token_url = settings.generate_token_url
    else:
        pin = _read_secret("DHAN_PIN", "DHAN_PIN_FILE")
        totp_secret = _read_secret("DHAN_TOTP_SECRET", "DHAN_TOTP_SECRET_FILE")
        from brokers.dhan.settings import _GENERATE_TOKEN_URL
        token_url = _GENERATE_TOKEN_URL
    if not pin or not totp_secret:
        return None
    try:
        import pyotp
        import requests as _requests
        totp_code = pyotp.TOTP(totp_secret).now()
        client_id = settings.client_id if settings else os.environ.get("DHAN_CLIENT_ID", "")
        params = {"dhanClientId": client_id, "pin": pin, "totp": totp_code}
        url = f"{token_url}?{urlencode(params)}"
        resp = _requests.post(url, timeout=15)
        if resp.status_code != 200:
            logger.warning("TOTP token generation failed: HTTP %d", resp.status_code)
            return None
        body = resp.json()
        data = body.get("data", body)
        result: str = data.get("accessToken") or data.get("access_token") or ""
        return result or None
    except Exception as exc:
        logger.warning("TOTP token generation failed: %s", exc)
        return None


def _read_secret(env_key: str, file_key: str) -> str | None:
    """Read a secret from env var or file."""
    val = os.environ.get(env_key, "")
    if val:
        return val
    file_path = os.environ.get(file_key, "")
    if file_path and Path(file_path).exists():
        return Path(file_path).read_text().strip()
    return None


def _update_env_token(env_path: Path, token: str) -> None:
    """Update DHAN_ACCESS_TOKEN in the env file atomically.

    Uses ``fcntl.flock`` for cross-process exclusion and a temp-file +
    ``os.replace`` so readers never see a partially-written file. If the
    token key is missing, it is appended while preserving all other keys,
    comments, and blank lines.
    """
    if not env_path.exists():
        return

    try:
        import fcntl
    except Exception as exc:  # pragma: no cover - non-Unix fallback
        logger.warning("fcntl unavailable, env update unprotected: %s", exc)
        return

    fd: int | None = None
    tmp_path = env_path.with_suffix(f"{env_path.suffix}.tmp")
    try:
        # Hold an exclusive lock on the env file while we read and replace it.
        fd = os.open(str(env_path), os.O_RDWR | os.O_CREAT, 0o600)
        fcntl.flock(fd, fcntl.LOCK_EX)

        with os.fdopen(fd, "r", encoding="utf-8", closefd=False) as fh:
            content = fh.read()

        lines = content.splitlines()
        updated = False
        for i, line in enumerate(lines):
            if line.startswith("DHAN_ACCESS_TOKEN="):
                lines[i] = f"DHAN_ACCESS_TOKEN={token}"
                updated = True
                break
        if not updated:
            # Preserve a trailing blank line when appending if the file ends
            # without a newline; otherwise just append the new key.
            if lines and not content.endswith("\n"):
                lines.append("")
            lines.append(f"DHAN_ACCESS_TOKEN={token}")

        new_content = "\n".join(lines)
        if not new_content.endswith("\n"):
            new_content += "\n"

        tmp_path.write_text(new_content, encoding="utf-8")
        # fsync temp file contents before the atomic rename.
        with open(tmp_path, "rb") as tmp_fh:
            os.fsync(tmp_fh.fileno())
        # fsync the directory so the rename is durable.
        dir_fd = os.open(env_path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(dir_fd)
        finally:
            os.close(dir_fd)

        os.replace(tmp_path, env_path)
    except PermissionError:
        # Env file is read-only (e.g. credentials managed externally). Persist
        # the new token via the JsonTokenStateStore instead and continue.
        logger.info("Env file is read-only; token persisted to state store only.")
    except Exception as exc:
        logger.warning("Failed to update env token: %s", exc)
        if tmp_path.exists():
            tmp_path.unlink()
    finally:
        if fd is not None:
            try:
                fcntl.flock(fd, fcntl.LOCK_UN)
            except Exception as exc:
                logger.debug("file_unlock_failed: %s", exc)
            try:
                os.close(fd)
            except Exception as exc:
                logger.debug("file_close_failed: %s", exc)


