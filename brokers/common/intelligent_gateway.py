"""Intelligent Gateway — combines Dhan and Upstox for optimal performance.

Routes requests to the fastest broker for each operation type.
Supports parallel data fetching for batch operations.

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
from decimal import Decimal
from typing import Any

import pandas as pd

from brokers.common.core.domain import FundLimits, MarketDepth, Quote
from brokers.common.observability.event_metrics import EventMetrics

logger = logging.getLogger(__name__)

_RAISE = object()  # sentinel for _route() default="raise RuntimeError"


class IntelligentGateway:
    """Combines Dhan and Upstox for optimal performance.

    Routing strategy:
    - LTP/Quote: Upstox (faster batch operations)
    - History: Dhan (better intraday support)
    - Option Chain: Dhan (more complete)
    - Future Chain: Dhan (Upstox doesn't support)
    - Depth: Dhan (Upstox endpoint deprecated)
    - Positions/Holdings/Funds: Use first available
    """

    def __init__(
        self,
        dhan_gateway=None,
        upstox_gateway=None,
        metrics: EventMetrics | None = None,
    ) -> None:
        self._dhan = dhan_gateway
        self._upstox = upstox_gateway
        self._metrics = metrics or EventMetrics()

    @property
    def dhan(self):
        return self._dhan

    @property
    def upstox(self):
        return self._upstox

    @property
    def metrics(self) -> EventMetrics:
        return self._metrics

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
        """Route *operation* to the primary broker gateway, falling back on failure.

        On primary failure: logs a WARNING + increments a fallback metric,
        then tries the fallback broker (if configured). If both fail or no
        brokers are available, returns *default* or raises RuntimeError.
        """
        primary_gw = getattr(self, f"_{primary}", None)
        if primary_gw:
            try:
                return getattr(primary_gw, operation)(*args, **kwargs)
            except Exception as exc:
                self._log_fallback(operation, primary, exc)

        if fallback is not None:
            fallback_gw = getattr(self, f"_{fallback}", None)
            if fallback_gw:
                return getattr(fallback_gw, operation)(*args, **kwargs)

        if default is not _RAISE:
            return default
        raise RuntimeError("No broker available")

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
