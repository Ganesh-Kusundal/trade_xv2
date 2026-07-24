"""DhanConnection — owns auth, transport, rate limiter, sub-adapters."""

from __future__ import annotations

import threading
from collections.abc import Callable
from typing import Any

from domain.ports.types import BrokerSnapshot
from plugins.brokers.common.circuit_breaker import CircuitBreakerConfig
from plugins.brokers.common.liveness import ConnectionLiveness
from plugins.brokers.common.rate_limit import limiter_from_profile
from plugins.brokers.common.retry import RetryConfig
from plugins.brokers.common.token_lifecycle import TokenRefreshScheduler
from plugins.brokers.common.master_lifecycle import InstrumentRefreshScheduler
from plugins.brokers.common.transport import BaseTransport, HttpTransport
from plugins.brokers.dhan.adapters import (
    DhanInstrumentAdapter,
    DhanMarketDataAdapter,
    DhanOrdersAdapter,
    DhanPortfolioAdapter,
    DhanStreamingAdapter,
)
from plugins.brokers.dhan.auth import DhanTokenManager
from plugins.brokers.dhan.config import DhanConfig
from plugins.brokers.dhan.wire import DhanWire


class DhanConnection(ConnectionLiveness):
    def __init__(
        self,
        config: DhanConfig | None = None,
        transport: BaseTransport | None = None,
        token_manager: DhanTokenManager | None = None,
        ws_factory: Callable[[str], Any] | None = None,
        rate_limit_profile: Any | None = None,
    ) -> None:
        self.config = config or DhanConfig()
        self.wire = DhanWire(client_id=self.config.client_id)
        self._tokens = token_manager or DhanTokenManager(self.config)
        self._scheduler = TokenRefreshScheduler(
            "dhan",
            self._tokens,
            broadcast=self._tokens._broadcast,
            interval_seconds=300.0,
        )
        # Daily instrument-master refresh (tokenless CDN; best-effort). Starts
        # with connect(); keeps the on-disk cache fresh without a gateway call.
        self._instrument_scheduler = InstrumentRefreshScheduler("dhan", self)
        # Rate limits sourced from RateLimitProfile when provided;
        # limiter_from_profile falls back to the DHAN table constants otherwise.
        self._limiter = limiter_from_profile("dhan", rate_limit_profile)
        if transport is not None:
            self.transport = transport
        else:
            self.transport = HttpTransport(
                base_url=self.config.base_url,
                limiter=self._limiter,
                token_provider=self._tokens.ensure_token,
                # Dhan uses access-token + client-id headers (not Bearer)
                auth_header="access-token",
                auth_prefix="",
                extra_headers={
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                    "client-id": self.config.client_id,
                },
                circuit_breaker_config=CircuitBreakerConfig(
                    failure_threshold=5,
                    recovery_timeout=30.0,
                    success_threshold=2,
                ),
                retry_config=RetryConfig(
                    max_retries=3,
                    base_delay=0.5,
                    max_delay=10.0,
                    exponential_base=2.0,
                    jitter=True,
                    retryable_status=(429, 500, 502, 503, 504),
                ),
                on_auth_failure=self._reauth_on_401,
            )
        self.orders = DhanOrdersAdapter(self.transport, self.wire)
        self.market_data = DhanMarketDataAdapter(self.transport, self.wire)
        self.portfolio = DhanPortfolioAdapter(self.transport, self.wire)
        self.instruments = DhanInstrumentAdapter(self.transport, self.wire)
        self.streaming = DhanStreamingAdapter(
            wire=self.wire,
            ws_url=self.config.ws_url,
            token_provider=self._tokens.ensure_token,
            client_id=self.config.client_id,
            ws_factory=ws_factory,
        )
        self._connected = False
        self._authenticated = False
        self._last_auth_error: Exception | None = None
        self._instruments_loaded = False
        self._instruments_lock = threading.Lock()

    def _reauth_on_401(self) -> bool:
        """Called by HttpTransport on HTTP 401/403. Force-refresh token once."""
        try:
            self._tokens.ensure_token(force_refresh=True)
            return True
        except Exception:
            return False

    def connect(self) -> None:
        self._connected = True
        self._scheduler.start()
        self._instrument_scheduler.start()

    def authenticate(self) -> bool:
        try:
            token = self._tokens.ensure_token()
            self._authenticated = bool(token)
            if not self._authenticated:
                return False
            try:
                self.portfolio.get_funds()
            except Exception as exc:
                msg = str(exc)
                if "401" in msg or "400" in msg or "DH-901" in msg or "DH-906" in msg or "Invalid_Authentication" in msg or "Invalid Token" in msg:
                    if not self.config.has_totp:
                        raise
                    try:
                        self._tokens.ensure_token(force_refresh=True)
                        self.portfolio.get_funds()
                    except Exception as refresh_exc:
                        # ponytail: if TOTP cooldown blocks refresh, surface original auth error
                        raise refresh_exc from exc
                else:
                    raise
            self._authenticated = True
            return True
        except Exception as exc:
            self._last_auth_error = exc
            self._authenticated = False
            return False

    def disconnect(self) -> None:
        self._scheduler.stop()
        self._instrument_scheduler.stop()
        self.streaming.close()
        self._connected = False
        self._authenticated = False

    def load_instruments(self) -> None:
        self.instruments.load_instruments()

    def ensure_fresh(self, *, force_refresh: bool = False) -> None:
        """Lazy single-flight instrument load — safe to call on every gateway call.

        The first call (or any call with ``force_refresh=True``) downloads and
        registers the scrip master; subsequent calls are no-ops until the daily
        scheduler passes ``force_refresh=True``. Guarded by a lock so concurrent
        first calls don't double-download.
        """
        if not force_refresh and self._instruments_loaded:
            return
        with self._instruments_lock:
            # Re-check under lock: a racing thread may have loaded while we waited.
            if not force_refresh and self._instruments_loaded:
                return
            self.instruments.load_instruments(force_refresh=force_refresh)
            self._instruments_loaded = True

    def mass_status(self) -> BrokerSnapshot:
        return BrokerSnapshot(
            orders=self.orders.get_orderbook(),
            positions=self.portfolio.get_positions(),
            account=self.portfolio.get_funds(),
        )

    def token_status(self) -> dict[str, object]:
        """Token health for a liveness probe / warning before mid-session expiry."""
        return self._tokens.token_status()
