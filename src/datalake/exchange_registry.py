"""Exchange registry — datalake's access point for the active exchange adapter.

ADR-005 / P5-2 (G3). The datalake reads exchange conventions ONLY through this
module, never from hardcoded constants. At startup, ``wire_exchange_plugins()``
loads exchange plugins from the ``tradex.exchanges`` entry-point group.
Until an adapter is registered, :func:`get_active_adapter` raises
:class:`ExchangeNotConfigured`.
"""

from __future__ import annotations

import importlib
import logging
import os
import threading
from datetime import date, timedelta
from importlib.metadata import entry_points
from typing import TYPE_CHECKING

from domain.exceptions import ExchangeNotConfigured

if TYPE_CHECKING:
    from datetime import time

    from domain.ports.exchange_adapter import ExchangeAdapter
    from domain.ports.exchange_calendar import TradingCalendar

logger = logging.getLogger(__name__)

_ENTRY_POINT_GROUP = "tradex.exchanges"

#: Fraction of expected candles required for a day/chunk to count as complete.
COMPLETENESS_OK_FRACTION: float = 0.90

_TIMEFRAME_MINUTES: dict[str, int] = {
    "1m": 1,
    "5m": 5,
    "15m": 15,
    "30m": 30,
    "1h": 60,
    "1d": 1440,
}


class _ExchangeState:
    """Module-level exchange adapter state."""

    _active_adapter: ExchangeAdapter | None = None
    _discovered = False
    _lock = threading.Lock()

    @classmethod
    def set_active(cls, adapter: ExchangeAdapter) -> None:
        cls._active_adapter = adapter

    @classmethod
    def get_active(cls) -> ExchangeAdapter:
        # discover() sets _discovered=True before _active_adapter is
        # populated (plugin import takes time). An *unlocked* fast-path
        # check here (even a "double-checked" one that only takes the
        # lock conditionally) is still racy: a concurrent thread can
        # observe _discovered=True and _active_adapter=None in the same
        # torn read -- the exact transitional state discover() passes
        # through -- and raise before the discovering thread finishes.
        # The lock must guard the whole read-check-return, not just the
        # discover() call; it's an uncontended stdlib Lock so the cost
        # per call is negligible next to any real broker I/O.
        with cls._lock:
            if cls._active_adapter is None and not cls._discovered:
                cls.discover()
            if cls._active_adapter is None:
                raise ExchangeNotConfigured(
                    "No exchange adapter registered. Install an exchange plugin "
                    "(e.g. ``pip install tradex[NSE]``) or call set_active_adapter()."
                )
            return cls._active_adapter

    @classmethod
    def discover(cls) -> list[str]:
        cls._discovered = True
        discovered: list[str] = []
        for ep in entry_points(group=_ENTRY_POINT_GROUP):
            try:
                mod = importlib.import_module(ep.value)
            except Exception:
                logger.warning(
                    "exchange_plugin_discovery_failed",
                    extra={"exchange_id": ep.name, "exchange_module": ep.value},
                    exc_info=True,
                )
                continue
            adapter = getattr(mod, "ADAPTER", None)
            if adapter is not None and cls._active_adapter is None:
                cls._active_adapter = adapter
                logger.info("exchange_plugin_loaded", extra={"exchange": adapter.exchange})
            discovered.append(ep.name)
        return discovered


def set_active_adapter(adapter: ExchangeAdapter) -> None:
    """Register the active exchange adapter (called by runtime/ at startup)."""
    _ExchangeState.set_active(adapter)


def get_active_adapter() -> ExchangeAdapter:
    """Return the active exchange adapter.

    Raises :class:`ExchangeNotConfigured` if no adapter has been registered.
    """
    return _ExchangeState.get_active()


def get_active_exchange_code() -> str:
    """Shorthand: return the canonical exchange code (e.g. ``'NSE'``)."""
    return get_active_adapter().exchange


def discover_exchanges() -> list[str]:
    """Import every exchange package registered under ``tradex.exchanges``.

    Each exchange plugin module must expose a module-level ``ADAPTER``
    (an :class:`ExchangeAdapter` instance) and a ``CALENDAR``
    (a :class:`TradingCalendar` instance). The first discovered adapter
    becomes the active one.

    Returns the list of successfully discovered exchange ids.
    """
    return _ExchangeState.discover()


def wire_exchange_plugins() -> None:
    """Discover ``tradex.exchanges`` plugins; register bundled NSE when configured.

    Called from the runtime composition root. When no plugin is discovered and
    ``TRADEX_LEGACY_NSE_DEFAULT=1`` (default), the bundled NSE adapter is
    registered with a warning log (ponytail: remove after soak).
    """
    discover_exchanges()
    if _ExchangeState._active_adapter is not None:
        return
    legacy = (os.getenv("TRADEX_LEGACY_NSE_DEFAULT") or "1").strip() == "1"
    if not legacy:
        return
    logger.warning(
        "No tradex.exchanges plugin discovered; registering bundled NSE adapter "
        "(set TRADEX_LEGACY_NSE_DEFAULT=0 to fail closed)"
    )
    from plugins.exchanges.nse import ADAPTER

    set_active_adapter(ADAPTER)


# ---------------------------------------------------------------------------
# Calendar helpers — derive session constants from the active adapter's
# TradingCalendar instead of hardcoding NSE values in datalake/core.
# ---------------------------------------------------------------------------


def _get_calendar() -> TradingCalendar:
    """Return the active adapter's TradingCalendar, or raise."""
    from domain.ports.exchange_calendar import TradingCalendar

    adapter = get_active_adapter()
    calendar = getattr(adapter, "calendar", None)
    if calendar is None or not isinstance(calendar, TradingCalendar):
        raise ExchangeNotConfigured(
            "Active exchange adapter has no TradingCalendar. "
            "Install an exchange plugin that provides one."
        )
    return calendar


def get_market_open_time() -> time:
    """Return the market open time for the active exchange."""

    bounds = _get_calendar().session_bounds(None)
    return bounds[0]


def get_market_close_time() -> time:
    """Return the market close time for the active exchange."""

    bounds = _get_calendar().session_bounds(None)
    return bounds[1]


def get_session_minutes() -> int:
    """Return the total session minutes for the active exchange."""
    bounds = _get_calendar().session_bounds(None)
    open_m = bounds[0].hour * 60 + bounds[0].minute
    close_m = bounds[1].hour * 60 + bounds[1].minute
    return close_m - open_m


def get_expected_candles_per_day() -> int:
    """Return expected 1-minute candles per full trading day."""
    return get_session_minutes()


def is_trading_day(d: date) -> bool:
    """Return True when ``d`` is a trading day on the active exchange."""
    return _get_calendar().is_trading_day(d)


def trading_days_between(start: date, end: date) -> list[date]:
    """Return trading days between *start* and *end* inclusive."""
    days: list[date] = []
    current = start
    while current <= end:
        if is_trading_day(current):
            days.append(current)
        current += timedelta(days=1)
    return days


def count_trading_days(start: date, end: date) -> int:
    """Count trading days between *start* and *end* inclusive."""
    return len(trading_days_between(start, end))


def expected_candles_per_day(timeframe: str = "1m", *, early_close: bool = False) -> int:
    """Expected candle count for a full session and timeframe."""
    # ponytail: early-close not on TradingCalendar port yet; 255m session when flagged.
    minutes = 255 if early_close else get_session_minutes()
    return minutes // _TIMEFRAME_MINUTES.get(timeframe, 1)


def expected_candles(d: date, timeframe: str = "1m") -> int:
    """Expected candle count for trading day *d* and *timeframe*."""
    if not is_trading_day(d):
        return 0
    return expected_candles_per_day(timeframe)
