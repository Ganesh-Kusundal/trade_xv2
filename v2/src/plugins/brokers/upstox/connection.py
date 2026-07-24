"""UpstoxConnection — auth + transport + sub-adapters."""

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
from plugins.brokers.upstox.adapters import (
    UpstoxInstrumentAdapter,
    UpstoxMarketDataAdapter,
    UpstoxOrdersAdapter,
    UpstoxPortfolioAdapter,
    UpstoxStreamingAdapter,
)
from plugins.brokers.upstox.auth import UpstoxTokenManager
from plugins.brokers.upstox.config import UpstoxConfig
from plugins.brokers.upstox.wire import UpstoxWire


class UpstoxConnection(ConnectionLiveness):
    def __init__(
        self,
        config: UpstoxConfig | None = None,
        transport: BaseTransport | None = None,
        token_manager: UpstoxTokenManager | None = None,
        ws_factory: Callable[[str], Any] | None = None,
        rate_limit_profile: Any | None = None,
    ) -> None:
        self.config = config or UpstoxConfig()
        self.wire = UpstoxWire()
        self._tokens = token_manager or UpstoxTokenManager(self.config)
        self._scheduler = TokenRefreshScheduler(
            "upstox",
            self._tokens,
            broadcast=self._tokens._broadcast,
            interval_seconds=300.0,
        )
        # Daily instrument-master refresh (tokenless CDN; best-effort). Starts
        # with connect(); keeps the on-disk cache fresh without a gateway call.
        self._instrument_scheduler = InstrumentRefreshScheduler("upstox", self)
        # Rate limits sourced from RateLimitProfile when provided;
        # limiter_from_profile falls back to the UPSTOX table constants otherwise.
        self._limiter = limiter_from_profile("upstox", rate_limit_profile)
        if transport is not None:
            self.transport = transport
        else:
            self.transport = HttpTransport(
                base_url=self.config.base_url,
                limiter=self._limiter,
                token_provider=self._tokens.ensure_token,
                auth_header="Authorization",
                auth_prefix="Bearer ",
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
        self.orders = UpstoxOrdersAdapter(self.transport, self.wire)
        self.market_data = UpstoxMarketDataAdapter(self.transport, self.wire)
        self.portfolio = UpstoxPortfolioAdapter(self.transport, self.wire, config=self.config)
        self.instruments = UpstoxInstrumentAdapter(self.transport, self.wire)
        self.streaming = UpstoxStreamingAdapter(
            wire=self.wire,
            ws_url=self.config.ws_url,
            token_provider=self._tokens.ensure_token,
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
                self.portfolio.get_profile()
            except Exception as exc:
                msg = str(exc)
                # Cloudflare / WAF blocks are not fixed by TOTP
                if "1010" in msg or "error code: 1010" in msg:
                    raise
                if "401" in msg or "Unauthorized" in msg or "UDAPI100050" in msg:
                    if self.config.has_totp or self.config.refresh_token:
                        # Store/env may look unexpired but broker already revoked it
                        self._tokens.ensure_token(force_refresh=True)
                        self.portfolio.get_profile()
                    else:
                        raise
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
        registers the complete.json master; subsequent calls are no-ops until
        the daily scheduler passes ``force_refresh=True``. Guarded by a lock so
        concurrent first calls don't double-download.
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
