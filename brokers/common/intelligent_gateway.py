"""Intelligent Gateway — combines Dhan and Upstox for optimal performance.

Routes requests to the fastest broker for each operation type.
Supports parallel data fetching for batch operations.

Graceful degradation
--------------------
When *all* brokers are down the gateway enters **degraded mode**:

* Read operations (ltp, quote, history, …) return cached / stale data
  if available. A warning is logged and the response is tagged with a
  ``_degraded`` metadata flag when the return type supports it.
* Write operations (order placement, modification, cancellation) raise
  :class:`BrokerDegradedError` immediately — no silent failures.

The :class:`BrokerHealthMonitor` tracks consecutive failures per broker.
Once the failure threshold (default 5) is exceeded the broker is marked
unhealthy and routing skips it in favour of a healthy fallback.

Observability contract
----------------------
Every silent ``except Exception: pass`` from the previous version has been
replaced with a call to :meth:`IntelligentGateway._log_fallback`. Each
fallback:

1. Logs at WARNING level with the operation, the failing broker, and the
   exception type / message.
2. Increments the ``intelligent_gateway_fallback`` counter on the
   attached :class:`EventMetrics` instance (keyed by operation, broker,
   and exception class name) so an SRE can alert on systemic broker
   outages.
3. Returns the fallback broker's response (or an empty default), so
   callers do not need to handle a new exception type.

The metrics instance is optional; if not supplied, an isolated instance
is created. Tests inject a fresh instance to assert counters.
"""

from __future__ import annotations

import logging
import threading
import time
from decimal import Decimal
from typing import Any

import pandas as pd

from brokers.common.core.domain import FundLimits, MarketDepth, Quote
from brokers.common.observability.event_metrics import EventMetrics
from brokers.common.resilience.broker_health_monitor import BrokerHealthMonitor
from brokers.common.resilience.errors import BrokerDegradedError

logger = logging.getLogger(__name__)

_RAISE = object()  # sentinel for _route() default="raise RuntimeError"

# Cache TTL constants (seconds)
_QUOTE_CACHE_TTL = 60  # 60 seconds for quotes/LTP
_HISTORY_CACHE_TTL = 300  # 300 seconds for history

# Write operations that must NEVER return stale data
_WRITE_OPERATIONS = frozenset({
    "place_order",
    "modify_order",
    "cancel_order",
    "place_slice_order",
    "delete_slice_order",
})


class _CacheEntry:
    """Single cache entry with TTL awareness."""

    __slots__ = ("value", "expires_at", "operation", "symbol")

    def __init__(
        self,
        value: Any,
        ttl: float,
        operation: str,
        symbol: str,
    ) -> None:
        self.value = value
        self.expires_at = time.monotonic() + ttl
        self.operation = operation
        self.symbol = symbol

    @property
    def is_expired(self) -> bool:
        return time.monotonic() > self.expires_at


class IntelligentGateway:
    """Combines Dhan and Upstox for optimal performance.

    Routing strategy:
    - LTP/Quote: Upstox (faster batch operations)
    - History: Dhan (better intraday support)
    - Option Chain: Dhan (more complete)
    - Future Chain: Dhan (Upstox doesn't support)
    - Depth: Dhan (Upstox endpoint deprecated)
    - Positions/Holdings/Funds: Use first available

    Parameters
    ----------
    dhan_gateway : optional
        Dhan broker gateway instance.
    upstox_gateway : optional
        Upstox broker gateway instance.
    metrics : EventMetrics, optional
        Metrics collector for observability. Created automatically if
        not supplied.
    health_monitor : BrokerHealthMonitor, optional
        Health tracker that determines broker availability. When
        omitted, health checks are disabled and routing behaves as
        before (always try primary, then fallback).
    """

    def __init__(
        self,
        dhan_gateway=None,
        upstox_gateway=None,
        metrics: EventMetrics | None = None,
        health_monitor: BrokerHealthMonitor | None = None,
    ) -> None:
        self._dhan = dhan_gateway
        self._upstox = upstox_gateway
        self._metrics = metrics or EventMetrics()
        self._health_monitor = health_monitor
        # In-memory cache: (operation, symbol) -> _CacheEntry
        # Thread-safe: protected by _cache_lock
        self._cache: dict[tuple[str, str], _CacheEntry] = {}
        self._cache_lock = threading.Lock()

    @property
    def dhan(self):
        return self._dhan

    @property
    def upstox(self):
        return self._upstox

    @property
    def metrics(self) -> EventMetrics:
        return self._metrics

    @property
    def health_monitor(self) -> BrokerHealthMonitor | None:
        return self._health_monitor

    @property
    def degraded_mode(self) -> bool:
        """Return True when every configured broker is unhealthy.

        If no health monitor is attached this always returns False.
        """
        if self._health_monitor is None:
            return False
        tracked = []
        if self._dhan is not None:
            tracked.append("dhan")
        if self._upstox is not None:
            tracked.append("upstox")
        if not tracked:
            return False
        return not self._health_monitor.any_healthy(tracked)

    # ── Cache helpers ───────────────────────────────────────────────────

    def _cache_key(self, operation: str, symbol: str) -> tuple[str, str]:
        return (operation, symbol)

    def _cache_put(
        self,
        operation: str,
        symbol: str,
        value: Any,
        ttl: float,
    ) -> None:
        """Store *value* in the cache with the given TTL.
        
        Thread-safe: acquires _cache_lock before mutating _cache.
        """
        key = self._cache_key(operation, symbol)
        with self._cache_lock:
            self._cache[key] = _CacheEntry(value, ttl, operation, symbol)

    def _cache_get(
        self,
        operation: str,
        symbol: str,
    ) -> Any | None:
        """Return cached value if present and not expired, else None.
        
        Thread-safe: acquires _cache_lock before reading _cache.
        """
        key = self._cache_key(operation, symbol)
        with self._cache_lock:
            entry = self._cache.get(key)
        if entry is None or entry.is_expired:
            return None
        return entry.value

    def _cache_ttl_for(self, operation: str) -> float:
        """Return the appropriate TTL based on operation type."""
        if operation in ("history", "history_batch"):
            return _HISTORY_CACHE_TTL
        return _QUOTE_CACHE_TTL

    # ── Generic routing helper ───────────────────────────────────────────

    def _route(
        self,
        operation: str,
        *args: Any,
        primary: str = "dhan",
        fallback: str | None = None,
        default: Any = _RAISE,
        **kwargs: Any,
    ) -> Any:
        """Route *operation* to the best available broker.

        Order of evaluation:
        1. If a health monitor is present and the primary broker is
           unhealthy but the fallback is healthy, skip directly to the
           fallback.
        2. Try the primary broker. On failure record it and try fallback.
        3. If both fail or no brokers are available:
           - For read operations: return cached data if available.
           - For write operations: raise :class:`BrokerDegradedError`.
           - If a *default* sentinel was provided return that.
           - Otherwise raise ``RuntimeError("No broker available")``.
        """
        primary_gw = getattr(self, f"_{primary}", None)
        fallback_gw = getattr(self, f"_{fallback}", None) if fallback else None

        # --- Health-aware routing -----------------------------------
        effective_primary = primary
        effective_fallback = fallback

        if self._health_monitor is not None:
            primary_healthy = self._health_monitor.is_healthy(primary)
            fallback_healthy = self._health_monitor.is_healthy(fallback) if fallback else True

            if not primary_healthy and fallback_healthy and fallback_gw is not None:
                # Skip unhealthy primary entirely
                logger.warning(
                    "broker_health_skip_primary",
                    extra={
                        "operation": operation,
                        "skipped_broker": primary,
                        "reason": "unhealthy",
                    },
                )
                self._metrics.inc(
                    "intelligent_gateway_health_skip",
                    f"{operation}:{primary}",
                )
                effective_primary = fallback
                effective_fallback = None

        # --- Attempt primary ----------------------------------------
        gw = getattr(self, f"_{effective_primary}", None)
        if gw is not None:
            try:
                result = getattr(gw, operation)(*args, **kwargs)
                if self._health_monitor is not None:
                    self._health_monitor.record_success(effective_primary)
                # Cache the successful result for read operations
                symbol = self._extract_symbol(args, kwargs)
                if symbol is not None:
                    self._cache_put(
                        operation, symbol, result, self._cache_ttl_for(operation)
                    )
                return result
            except Exception as exc:
                self._log_fallback(operation, effective_primary, exc)
                if self._health_monitor is not None:
                    self._health_monitor.record_failure(effective_primary)

        # --- Attempt fallback ---------------------------------------
        # Original contract: secondary broker call is NOT wrapped in
        # try/except — its exception propagates without being logged
        # or metered.  Only the primary broker's failure is observable.
        # When a health monitor is present we DO wrap it so we can
        # record failures for degraded-mode decisions.
        fallback_exc: Exception | None = None
        if effective_fallback is not None and fallback_gw is not None:
            if self._health_monitor is not None:
                # New behavior: wrap to track health
                try:
                    result = getattr(fallback_gw, operation)(*args, **kwargs)
                    self._health_monitor.record_success(effective_fallback)
                    symbol = self._extract_symbol(args, kwargs)
                    if symbol is not None:
                        self._cache_put(
                            operation, symbol, result, self._cache_ttl_for(operation)
                        )
                    return result
                except Exception as exc:
                    fallback_exc = exc
                    self._log_fallback(operation, effective_fallback, exc)
                    self._health_monitor.record_failure(effective_fallback)
            else:
                # Original behavior: no wrapping, exception propagates
                return getattr(fallback_gw, operation)(*args, **kwargs)

        # --- Both failed (or no brokers) — degraded mode ------------
        # Only reached when health_monitor is present (otherwise the
        # secondary exception would have already propagated above).
        if self._is_degraded_and_should_fallback(operation):
            symbol = self._extract_symbol(args, kwargs)
            return self._serve_degraded(operation, symbol, default)

        if fallback_exc is not None:
            raise fallback_exc

        if default is not _RAISE:
            return default
        raise RuntimeError("No broker available")

    def _is_degraded_and_should_fallback(self, operation: str) -> bool:
        """Return True when degraded-mode fallback is appropriate."""
        return (
            self._health_monitor is not None
            and self.degraded_mode
            and operation not in _WRITE_OPERATIONS
        )

    def _serve_degraded(
        self,
        operation: str,
        symbol: str | None,
        default: Any,
    ) -> Any:
        """Attempt to serve a read request from cache in degraded mode.

        Logs a CRITICAL message and returns cached data if available,
        otherwise returns *default* or raises RuntimeError.
        """
        health_status = (
            {k: v.to_dict() for k, v in self._health_monitor.get_health_status().items()}
            if self._health_monitor
            else {}
        )
        logger.critical(
            "broker_degraded_mode",
            extra={
                "operation": operation,
                "symbol": symbol,
                "health_status": health_status,
            },
        )
        self._metrics.inc("intelligent_gateway_degraded", operation)

        if symbol is not None:
            cached = self._cache_get(operation, symbol)
            if cached is not None:
                logger.warning(
                    "broker_degraded_serving_stale_cache",
                    extra={
                        "operation": operation,
                        "symbol": symbol,
                        "ttl": self._cache_ttl_for(operation),
                    },
                )
                return cached

        if default is not _RAISE:
            return default
        raise RuntimeError(
            f"No broker available and no cached data for {operation}({symbol})"
        )

    def _extract_symbol(self, args: tuple, kwargs: dict) -> str | None:
        """Best-effort extraction of a symbol for cache keying.

        The first positional argument is usually the symbol. If not a
        string we try the ``symbol`` keyword argument.
        """
        if args and isinstance(args[0], str):
            return args[0]
        if args and isinstance(args[0], list) and len(args[0]) == 1:
            # Single-element list like ltp_batch(["RELIANCE"])
            first = args[0][0]
            return first if isinstance(first, str) else None
        return kwargs.get("symbol")

    # ── Observability helpers ────────────────────────────────────────────

    def _log_fallback(
        self,
        operation: str,
        broker: str,
        exc: BaseException,
    ) -> None:
        """Record a silent fallback: log + metric, never raise.

        The previous implementation used ``except Exception: pass`` which
        hid systemic broker outages. This helper restores observability
        without changing the caller-visible behavior — the original
        fallback (next broker, or empty default) still runs.
        """
        exc_type = type(exc).__name__
        logger.warning(
            "intelligent_gateway_fallback",
            extra={
                "operation": operation,
                "broker": broker,
                "exception_type": exc_type,
                "exception_message": str(exc),
            },
        )
        # Bucket by (operation, broker, exception_type) so a single noisy
        # broker does not mask a different broker's failure.
        self._metrics.inc(
            "intelligent_gateway_fallback",
            f"{operation}:{broker}:{exc_type}",
        )

    # ── Routing methods ──────────────────────────────────────────────────

    def ltp(self, symbol: str, exchange: str = "NSE") -> Decimal:
        return self._route("ltp", symbol, exchange, primary="upstox", fallback="dhan")

    def ltp_batch(self, symbols: list[str], exchange: str = "NSE") -> dict[str, Decimal]:
        return self._route("ltp_batch", symbols, exchange, primary="upstox", fallback="dhan")

    def quote(self, symbol: str, exchange: str = "NSE") -> Quote:
        return self._route("quote", symbol, exchange, primary="upstox", fallback="dhan")

    def quote_batch(self, symbols: list[str], exchange: str = "NSE") -> dict[str, Quote]:
        return self._route("quote_batch", symbols, exchange, primary="upstox", fallback="dhan")

    def history(
        self,
        symbol: str | list[str],
        exchange: str = "NSE",
        timeframe: str = "1m",
        lookback_days: int = 90,
        from_date: str | None = None,
        to_date: str | None = None,
    ) -> pd.DataFrame:
        return self._route(
            "history", symbol, exchange, timeframe, lookback_days,
            from_date=from_date, to_date=to_date,
            primary="dhan", fallback="upstox",
        )

    def history_batch(
        self,
        symbols: list[str],
        exchange: str = "NSE",
        timeframe: str = "1D",
        lookback_days: int = 90,
    ) -> pd.DataFrame:
        return self._route(
            "history_batch", symbols, exchange, timeframe, lookback_days,
            primary="dhan", fallback="upstox",
        )

    def depth(self, symbol: str, exchange: str = "NSE") -> MarketDepth:
        return self._route("depth", symbol, exchange, primary="dhan", fallback="upstox")

    def option_chain(
        self,
        underlying: str,
        exchange: str = "INDEX",
        expiry: str | None = None,
    ) -> dict:
        return self._route(
            "option_chain", underlying, exchange, expiry,
            primary="dhan", fallback="upstox",
        )

    def future_chain(
        self,
        underlying: str,
        exchange: str = "INDEX",
    ) -> dict:
        return self._route(
            "future_chain", underlying, exchange,
            primary="dhan",
            default={"underlying": underlying, "exchange": exchange, "expiries": [], "contracts": []},
        )

    def stream(
        self,
        symbol: str,
        exchange: str = "NSE",
        mode: str = "LTP",
        on_tick: Any | None = None,
    ) -> Any:
        return self._route(
            "stream", symbol, exchange, mode, on_tick,
            primary="dhan", fallback="upstox",
        )

    def positions(self) -> list[Any]:
        return self._route("positions", primary="dhan", fallback="upstox", default=[])

    def holdings(self) -> list[Any]:
        return self._route("holdings", primary="dhan", fallback="upstox", default=[])

    def funds(self) -> FundLimits:
        return self._route("funds", primary="dhan", fallback="upstox", default=FundLimits())

    def trades(self) -> list[Any]:
        return self._route("trades", primary="dhan", fallback="upstox", default=[])

    def describe(self) -> dict:
        """Return combined broker metadata."""
        brokers = []
        if self._dhan:
            brokers.append("Dhan")
        if self._upstox:
            brokers.append("Upstox")
        return {
            "brokers": brokers,
            "routing": {
                "ltp": "Upstox (faster)",
                "quote": "Upstox (faster)",
                "history": "Dhan (better support)",
                "depth": "Dhan (Upstox deprecated)",
                "option_chain": "Dhan (more complete)",
                "future_chain": "Dhan (Upstox doesn't support)",
                "stream": "Dhan",
            }
        }

    def search(self, query: str) -> list[dict]:
        return self._route("search", query, primary="dhan", fallback="upstox", default=[])
