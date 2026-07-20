"""Exchange entity — defines trading venue metadata and session rules."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, time
from typing import NamedTuple


class TradingSession(NamedTuple):
    """A named trading window within a day (e.g. regular, pre-open, post-close)."""

    name: str
    open_time: time
    close_time: time


@dataclass(frozen=True, slots=True)
class Exchange:
    """Trading exchange entity — immutable definition of a venue.

    Encapsulates the exchange name, timezone, trading sessions, holidays,
    and supported product types.  Use ``is_trading_day`` to query whether
    a given date is a valid trading day for this exchange.
    """

    name: str
    timezone: str
    sessions: tuple[TradingSession, ...] = ()
    holidays: frozenset[date] = frozenset()
    products: frozenset[str] = frozenset()

    def is_trading_day(self, d: date) -> bool:
        """Return True if *d* is not a holiday (simple check — no weekend logic)."""
        return d not in self.holidays

    def __repr__(self) -> str:
        return (
            f"Exchange(name={self.name!r}, tz={self.timezone!r}, "
            f"sessions={len(self.sessions)}, holidays={len(self.holidays)})"
        )
