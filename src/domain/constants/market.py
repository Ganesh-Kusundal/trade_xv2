"""Market data constants — market hours, exchanges, tick sizes, and timezone.

All constants governing market hours, exchange identifiers, tick sizes,
and timezone definitions.
"""

from __future__ import annotations

from datetime import timedelta, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo

from domain.conventions import DEFAULT_MARKET_SURFACE

# ── Market data defaults (sourced from the default MarketSurface) ──────────
#
# These constants previously hardcoded NSE/INR/paisa assumptions inline. They
# now read their values from ``DEFAULT_MARKET_SURFACE`` (configured in
# ``config.profiles.market_surface``) so the conventions live in one place.
# The values are identical to the historical literals and are asserted equal
# by the test-suite.

#: Default tick size for FNO contracts (INR). **REQUIRES DOMAIN
#: VERIFICATION** — NSE FNO tick size can change. Both
#: ``core.Instrument.tick_size`` and ``services.CanonicalInstrument.tick_size``
#: should reference this.
DEFAULT_TICK_SIZE: Decimal = DEFAULT_MARKET_SURFACE.price_tick

#: Default trading currency (ISO-style code). Sourced from the surface.
DEFAULT_CURRENCY: str = DEFAULT_MARKET_SURFACE.currency

#: Default paisa-per-rupee price scale (sub-unit divisor) for the
#: paisa<->rupee convention. Sourced from the surface.
DEFAULT_PRICE_SCALE: int = DEFAULT_MARKET_SURFACE.price_scale

#: Default annual risk-free rate used by derivatives/P&L math. Sourced from
#: the surface.
DEFAULT_RISK_FREE_RATE: float = DEFAULT_MARKET_SURFACE.risk_free_rate

#: Default exchange segment for fall-through when EXCHANGE_TO_SEGMENT misses.
#: Broker-specific — the canonical canonical "NSE_EQ" wire code is owned by
#: each broker's segments module. This constant is the placeholder string
#: used in the few places that need a literal and cannot import the broker
#: module.
DEFAULT_EXCHANGE_SEGMENT_FALLBACK: str = "NSE_EQ"

#: Default exchange identifier (no wire suffix) used in helpers that do not
#: know the broker. Same caveat as above.
DEFAULT_EXCHANGE: str = DEFAULT_MARKET_SURFACE.exchange

#: Default derivatives exchange short code (NFO segment).
DEFAULT_DERIVATIVES_EXCHANGE: str = "NFO"

# ── Market hours (NSE equity) ──────────────────────────────────────────────

#: NSE equity market open hour (24h IST).
NSE_OPEN_HOUR_IST: int = 9

#: NSE equity market open minute.
NSE_OPEN_MINUTE_IST: int = 15

#: NSE equity market close hour.
NSE_CLOSE_HOUR_IST: int = 15

#: NSE equity market close minute.
NSE_CLOSE_MINUTE_IST: int = 30

#: MCX commodity market open hour (24h IST).
MCX_OPEN_HOUR_IST: int = 9

#: MCX commodity market open minute.
MCX_OPEN_MINUTE_IST: int = 0

#: MCX commodity market close hour.
MCX_CLOSE_HOUR_IST: int = 23

#: MCX commodity market close minute.
MCX_CLOSE_MINUTE_IST: int = 30

# ── Indicator defaults ───────────────────────────────────────────────────────

#: Default period for Average True Range (ATR) indicator.
#: Used by FeatureBuilder, backtest optimizer, and scanner queries.
ATR_PERIOD_DEFAULT: int = 14

#: Default period for RSI indicator.
RSI_PERIOD_DEFAULT: int = 14

#: Default window for SMA (Simple Moving Average).
SMA_WINDOW_DEFAULT: int = 20

# ── Timezone (IST = UTC+5:30, no DST) ─────────────────────────────────────

#: Fixed IST offset. Use this instead of ``timezone(timedelta(hours=5,
#: minutes=30))`` scattered across files. ``IST`` (below) is the preferred
#: public alternative; both represent the same offset.
IST_OFFSET = timezone(timedelta(hours=5, minutes=30))

#: Canonical IANA IST timezone. Import this instead of constructing
#: ``ZoneInfo("Asia/Kolkata")`` inline. Equivalent offset to ``IST_OFFSET``
#: but DST/history-aware via the tz database.
IST = ZoneInfo("Asia/Kolkata")

__all__ = [
    "ATR_PERIOD_DEFAULT",
    "DEFAULT_CURRENCY",
    "DEFAULT_DERIVATIVES_EXCHANGE",
    "DEFAULT_EXCHANGE",
    "DEFAULT_EXCHANGE_SEGMENT_FALLBACK",
    "DEFAULT_PRICE_SCALE",
    "DEFAULT_RISK_FREE_RATE",
    "DEFAULT_TICK_SIZE",
    "IST",
    "IST_OFFSET",
    "MCX_CLOSE_HOUR_IST",
    "MCX_CLOSE_MINUTE_IST",
    "MCX_OPEN_HOUR_IST",
    "MCX_OPEN_MINUTE_IST",
    "NSE_CLOSE_HOUR_IST",
    "NSE_CLOSE_MINUTE_IST",
    "NSE_OPEN_HOUR_IST",
    "NSE_OPEN_MINUTE_IST",
    "RSI_PERIOD_DEFAULT",
    "SMA_WINDOW_DEFAULT",
]
