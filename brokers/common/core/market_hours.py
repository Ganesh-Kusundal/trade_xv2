"""Market session hours (REF-3).

Single source of truth for the open/close hours of NSE equity,
BSE equity, MCX commodity, and NSE/BSE currency derivative
sessions. The previous design inlined ``(9, 15)`` / ``(15, 30)``
in 6+ files and the MCX session hours in another 3 places,
which is exactly the shotgun-surgery pattern the audit called
out.

All times are in **IST** (UTC+5:30, no DST). Use the helper
:func:`ist_now` to get a tz-aware current datetime in IST.

Domain verification
-------------------
* NSE/BSE equity: 09:15–15:30 IST (Mon–Fri, no holidays).
* MCX commodity: 09:00–23:30 IST (Mon–Fri, no holidays).
* NSE/BSE currency: 09:00–17:00 IST (Mon–Fri, no holidays).

These hours are taken from the NSE/BSE/MCX public trading
calendars. The set of **trading holidays** is intentionally
NOT modelled here — the broker's own ``market_status`` API is
the canonical source. The helper :func:`is_session_open` does
not check holidays; callers that need holiday awareness should
cross-check with ``broker.get_market_status()``.

Tests should be re-validated against the public exchange
calendars on a quarterly cadence.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timezone, timedelta

from brokers.common.core.constants import (
    IST_OFFSET,
    MCX_CLOSE_HOUR_IST,
    MCX_CLOSE_MINUTE_IST,
    MCX_OPEN_HOUR_IST,
    MCX_OPEN_MINUTE_IST,
    NSE_CLOSE_HOUR_IST,
    NSE_CLOSE_MINUTE_IST,
    NSE_OPEN_HOUR_IST,
    NSE_OPEN_MINUTE_IST,
)


# ── Session definitions ────────────────────────────────────────────────────


@dataclass(frozen=True)
class TradingSession:
    """A daily trading session for an exchange.

    All times are in IST. The session is open on Monday–Friday
    between ``open_time`` and ``close_time`` inclusive of
    ``open_time`` and exclusive of ``close_time`` (matching
    exchange convention: orders at the close instant are
    treated as next-session).
    """

    name: str
    open_time: time
    close_time: time

    def is_open(self, when: datetime | None = None) -> bool:
        """Return True if ``when`` (or now, if None) falls within the
        session on a weekday.

        Weekends (Sat=5, Sun=6) are never open. Holidays are NOT
        considered — see module docstring.
        """
        if when is None:
            when = ist_now()
        if when.tzinfo is None:
            # Treat naive datetimes as IST.
            when = when.replace(tzinfo=IST_OFFSET)
        # Convert to IST if a non-IST tz is provided.
        when_ist = when.astimezone(IST_OFFSET)
        if when_ist.weekday() >= 5:  # Sat=5, Sun=6
            return False
        t = when_ist.time()
        return self.open_time <= t < self.close_time


# ── Sessions (canonical) ───────────────────────────────────────────────────


NSE_EQUITY_SESSION = TradingSession(
    name="NSE_EQUITY",
    open_time=time(NSE_OPEN_HOUR_IST, NSE_OPEN_MINUTE_IST),
    close_time=time(NSE_CLOSE_HOUR_IST, NSE_CLOSE_MINUTE_IST),
)
# BSE equity shares the NSE session hours.
BSE_EQUITY_SESSION = TradingSession(
    name="BSE_EQUITY",
    open_time=time(NSE_OPEN_HOUR_IST, NSE_OPEN_MINUTE_IST),
    close_time=time(NSE_CLOSE_HOUR_IST, NSE_CLOSE_MINUTE_IST),
)
MCX_COMMODITY_SESSION = TradingSession(
    name="MCX_COMMODITY",
    open_time=time(MCX_OPEN_HOUR_IST, MCX_OPEN_MINUTE_IST),
    close_time=time(MCX_CLOSE_HOUR_IST, MCX_CLOSE_MINUTE_IST),
)
# NSE/BSE currency share the same hours (09:00–17:00 IST).
NSE_CURRENCY_SESSION = TradingSession(
    name="NSE_CURRENCY",
    open_time=time(9, 0),
    close_time=time(17, 0),
)
BSE_CURRENCY_SESSION = TradingSession(
    name="BSE_CURRENCY",
    open_time=time(9, 0),
    close_time=time(17, 0),
)


#: Registry of all known sessions, indexed by canonical name.
SESSIONS: dict[str, TradingSession] = {
    s.name: s
    for s in (
        NSE_EQUITY_SESSION,
        BSE_EQUITY_SESSION,
        MCX_COMMODITY_SESSION,
        NSE_CURRENCY_SESSION,
        BSE_CURRENCY_SESSION,
    )
}


# ── Helpers ────────────────────────────────────────────────────────────────


def ist_now() -> datetime:
    """Return the current datetime in IST (tz-aware)."""
    return datetime.now(tz=IST_OFFSET)


def is_session_open(session_name: str, when: datetime | None = None) -> bool:
    """Return True if the named session is open at ``when`` (or now)."""
    session = SESSIONS.get(session_name.upper())
    if session is None:
        raise KeyError(
            f"Unknown trading session: {session_name!r}. "
            f"Known sessions: {sorted(SESSIONS)}"
        )
    return session.is_open(when)


def is_equity_market_open(when: datetime | None = None) -> bool:
    """True if NSE or BSE equity session is open.

    NSE and BSE share the same hours so we check just one.
    """
    return NSE_EQUITY_SESSION.is_open(when)


def is_mcx_open(when: datetime | None = None) -> bool:
    """True if MCX commodity session is open."""
    return MCX_COMMODITY_SESSION.is_open(when)


__all__ = [
    "BSE_CURRENCY_SESSION",
    "BSE_EQUITY_SESSION",
    "MCX_COMMODITY_SESSION",
    "NSE_CURRENCY_SESSION",
    "NSE_EQUITY_SESSION",
    "SESSIONS",
    "TradingSession",
    "is_equity_market_open",
    "is_mcx_open",
    "is_session_open",
    "ist_now",
]
