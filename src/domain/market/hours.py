"""Canonical Indian exchange trading-session hours (IST).

Single source of truth for the regular-market session timings used across
the codebase. Previously the same ``time(9, 15)`` / ``time(15, 30)`` pair
was duplicated in three independent modules; any change (e.g. a new
muhurat session or an early-close convention) had to be applied in every
copy. Centralizing here means one edit propagates everywhere.

All times are IST-naive ``datetime.time`` values — callers that need a
timezone-aware instant must combine them with :data:`domain.constants.IST`.
"""

from __future__ import annotations

import os
from datetime import datetime, time, timedelta, timezone

# NSE/BSE equity + F&O regular continuous trading session (IST, naive).
NSE_EQUITY_OPEN: time = time(9, 15)
NSE_EQUITY_CLOSE: time = time(15, 30)

_IST = timezone(timedelta(hours=5, minutes=30))


def is_nse_market_open(now: datetime | None = None) -> bool:
    """True during NSE cash session (09:15–15:30 IST, Mon–Fri).

    ``FORCE_MARKET_OPEN=1`` overrides for CI / paper fill tests.
    """
    if os.environ.get("FORCE_MARKET_OPEN") == "1":
        return True
    now = now or datetime.now(tz=_IST)
    if now.tzinfo is None:
        now = now.replace(tzinfo=_IST)
    else:
        now = now.astimezone(_IST)
    if now.weekday() >= 5:
        return False
    t = now.time()
    return NSE_EQUITY_OPEN <= t < NSE_EQUITY_CLOSE
