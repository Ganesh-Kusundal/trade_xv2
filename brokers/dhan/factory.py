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

from tradex.runtime.auth import AuthManager, JsonTokenStateStore, TokenSource, TokenState
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
        cid = settings.client_id

        # ── Auth & token ───────────────────────────────────────────
        auth, token = self._create_auth(settings, env_path)

        # ── Per-instance refresh lock shared between the HTTP 401 handler and
        # the scheduler.  Created here (the natural owner) rather than inside
        # a helper so it does not need to be threaded through return values.
        refresh_lock = threading.Lock()

        # ── HTTP client ────────────────────────────────────────────
        client = self._create_http_client(
            settings, auth, cid, token, env_path, refresh_lock
        )

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

        # Register extension factories so brokers.common can find them

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

        # ── Health check registration ──────────────────────────────
        from tradex.runtime.observability.health_check import register_broker_health_check

        register_broker_health_check("dhan", gateway)

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
        from tradex.runtime.auth.token_ensure import ensure_access_token

        cid = settings.client_id
        token_state_dir = settings.resolved_token_state_dir
        token_state_dir.mkdir(parents=True, exist_ok=True)
        token_store = JsonTokenStateStore(token_state_dir / "dhan-token-state.json")

        def _generate_token() -> str | None:
            # Single mint path — always through TotpCooldownGuard.
            return _generate_totp_token(settings)

        auth = AuthManager(
            client_id=cid,
            token_store=token_store,
            token_source=TokenSource.TOTP,
            on_acquire=_generate_token,
            on_refresh=_generate_token,
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
                source=TokenSource.TOTP,
            )
        except Exception as exc:
            from brokers.dhan.exceptions import ConfigurationError

            raise ConfigurationError(
                f"DHAN_ACCESS_TOKEN not configured and TOTP refresh failed: {exc}"
            ) from exc

        if not state or not state.access_token:
            from brokers.dhan.exceptions import ConfigurationError

            raise ConfigurationError(
                "DHAN_ACCESS_TOKEN not configured and TOTP refresh failed"
            )

        # Hydrate AuthManager so 401 refresh / scheduler share the same state.
        auth._set_token(state.access_token, source=state.source)
        return auth, state.access_token

    def _create_http_client(
        self,
        settings: DhanConnectionSettings,
        auth: AuthManager,
        cid: str,
        token: str,
        env_file: Path,
        refresh_lock: threading.Lock,
    ) -> DhanHttpClient:
        """Create DhanHttpClient with standardized resilience patterns.

        Uses the Dhan resilience package for:
          - Per-category circuit breakers (orders, market_data, portfolio, admin)
          - Rate limiter with token bucket algorithm
          - Retry executor integration (via common resilience module)

        Maintains backward compatibility with existing read/write/admin
        circuit breaker naming used by the HTTP client and connection.
        """
        from brokers.dhan.config import DhanResilienceConfig, DEFAULT_CONFIG
        from brokers.dhan.config.config_loader import DhanConfigLoader
        from brokers.dhan.resilience import create_circuit_breakers
        from tradex.runtime.resilience.rate_limiter import create_rate_limiter
        from brokers.dhan.capabilities import dhan_capabilities

        # Load resilience configuration from settings or use defaults
        resilience_config = settings.resilience_config
        if resilience_config is None:
            # Try to load from environment
            resilience_config = DhanConfigLoader.load_from_environment()
            if resilience_config.to_dict() == DEFAULT_CONFIG.to_dict():
                # No custom config, use defaults
                resilience_config = DEFAULT_CONFIG

        # Create standardized circuit breakers with config-based thresholds
        # If resilience_config has custom circuit breaker settings, use them
        if resilience_config.circuit_breaker.orders_failure_threshold != 3 or \
           resilience_config.circuit_breaker.default_failure_threshold != 5:
            # Use custom thresholds
            from tradex.runtime.resilience.circuit_breaker import CircuitBreaker, CircuitBreakerConfig
            cbs = {
                "orders": CircuitBreaker(
                    "dhan-orders",
                    CircuitBreakerConfig(
                        failure_threshold=resilience_config.circuit_breaker.orders_failure_threshold,
                        success_threshold=resilience_config.circuit_breaker.success_threshold,
                        open_duration_ms=resilience_config.circuit_breaker.recovery_timeout_ms,
                    ),
                ),
                "market_data": CircuitBreaker(
                    "dhan-market-data",
                    CircuitBreakerConfig(
                        failure_threshold=resilience_config.circuit_breaker.default_failure_threshold,
                        success_threshold=resilience_config.circuit_breaker.success_threshold,
                        open_duration_ms=resilience_config.circuit_breaker.recovery_timeout_ms,
                    ),
                ),
                "portfolio": CircuitBreaker(
                    "dhan-portfolio",
                    CircuitBreakerConfig(
                        failure_threshold=resilience_config.circuit_breaker.default_failure_threshold,
                        success_threshold=resilience_config.circuit_breaker.success_threshold,
                        open_duration_ms=resilience_config.circuit_breaker.recovery_timeout_ms,
                    ),
                ),
                "admin": CircuitBreaker(
                    "dhan-admin",
                    CircuitBreakerConfig(
                        failure_threshold=resilience_config.circuit_breaker.default_failure_threshold,
                        success_threshold=resilience_config.circuit_breaker.success_threshold,
                        open_duration_ms=resilience_config.circuit_breaker.recovery_timeout_ms,
                    ),
                ),
            }
        else:
            # Use default circuit breakers
            cbs = create_circuit_breakers()

        # Map new categories to legacy names for backward compat:
        #   orders -> write_circuit_breaker
        #   market_data -> read_circuit_breaker
        #   portfolio + admin -> admin_circuit_breaker
        cb_orders = cbs["orders"]
        cb_market_data = cbs["market_data"]
        cbs["portfolio"]
        cb_admin = cbs["admin"]

        # Create rate limiter from Dhan's canonical RateLimitProfile values
        rate_limiter = create_rate_limiter("dhan", caps=dhan_capabilities())

        return DhanHttpClient(
            client_id=cid,
            access_token=token,
            base_url=settings.base_url,
            timeout=settings.http_timeout,
            enable_retry=settings.enable_retry,
            token_refresh_fn=lambda: _refresh_via_auth(auth, env_file, refresh_lock),
            # Pass resilience configuration
            config=resilience_config,
            # Legacy naming for backward compatibility with http_client.py
            read_circuit_breaker=cb_market_data,
            write_circuit_breaker=cb_orders,
            admin_circuit_breaker=cb_admin,
            # Store for observability
            _rate_limiter=rate_limiter,
            _circuit_breakers=cbs,
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
    ) -> DhanBrokerGateway:
        """Create DhanConnection + DhanBrokerGateway (transport facade)."""
        connection = DhanConnection(
            client=client,
            event_bus=event_bus,
            risk_manager=risk_manager,
            backfill_callback=backfill_callback,
            reconciliation_service=reconciliation_service,
            lifecycle=lifecycle,
            allow_live_orders=settings.allow_live_orders,
        )
        connection._auth = auth  # Store auth manager on connection
        from brokers.dhan.session_manager import DhanSessionManager

        connection._session_manager = DhanSessionManager(connection, auth)
        return DhanBrokerGateway(connection)

    def _wire_websocket_services(
        self,
        gateway: DhanBrokerGateway,
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
        gateway: DhanBrokerGateway,
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

        scheduler = TokenRefreshScheduler(
            auth=auth,
            interval_seconds=settings.scheduler_interval_seconds,
            buffer_seconds=settings.refresh_buffer_seconds,
            refresh_lock=refresh_lock,
            on_refresh=_on_token_refresh,
        )
        if lifecycle is not None:
            lifecycle.register(scheduler)
            gateway._conn.token_scheduler = scheduler
        else:
            import atexit

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
    from tradex.runtime.auth.token_persistence import TokenPersistence

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


def _next_token_expiry(now: Any, lifetime_seconds: int) -> Any:
    """Compute token expiry aligned to the next trading session end.

    Dhan tokens expire at the start of the next trading day (~06:00 IST /
    00:30 UTC).  If the current time is before today's 00:30 UTC, the
    expiry is today's 00:30; otherwise tomorrow's.  Falls back to a
    simple timedelta if the calculation fails.
    """
    from datetime import datetime, timedelta, timezone

    try:
        utc_now = datetime.now(timezone.utc) if now.tzinfo is None else now.astimezone(timezone.utc)
        session_end_today = utc_now.replace(hour=0, minute=30, second=0, microsecond=0)
        if utc_now < session_end_today:
            return session_end_today
        return session_end_today + timedelta(days=1)
    except (ValueError, TypeError, AttributeError) as exc:
        logger.warning("token_expiry_fallback", extra={"error": str(exc)})
        return now + timedelta(seconds=lifetime_seconds)


def _generate_totp_token(settings: DhanConnectionSettings | None = None) -> str | None:
    """Generate a fresh access token via TOTP (single path through TotpCooldownGuard).

    Delegates to :class:`DhanTotpClient` so factory, HTTP 401 refresh, and
    ad-hoc diagnostics share the same cooldown and broker rate-limit handling.
    """
    from brokers.dhan.auth.totp_client import DhanTotpClient
    from tradex.runtime.auth.totp_cooldown import TotpRateLimitError

    try:
        return DhanTotpClient(settings).generate()
    except TotpRateLimitError:
        raise
    except Exception as exc:
        logger.warning("TOTP token generation failed: %s", exc)
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
