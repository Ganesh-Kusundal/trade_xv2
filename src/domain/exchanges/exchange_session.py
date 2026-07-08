"""ExchangeSession value object — captures exchange session state.

An ExchangeSession describes a single exchange's trading session window
(market open/close times, segment, and whether the session is currently
active). This is a value object — immutable, identity-free, compared by
value.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import time


@dataclass(frozen=True)
class ExchangeSession:
    """Immutable exchange session descriptor."""

    exchange: str
    segment: str
    open_time: time
    close_time: time
    is_open: bool = False

    @property
    def key(self) -> str:
        return f"{self.exchange}:{self.segment}"

    def with_open(self) -> ExchangeSession:
        return ExchangeSession(
            exchange=self.exchange,
            segment=self.segment,
            open_time=self.open_time,
            close_time=self.close_time,
            is_open=True,
        )

    def with_closed(self) -> ExchangeSession:
        return ExchangeSession(
            exchange=self.exchange,
            segment=self.segment,
            open_time=self.open_time,
            close_time=self.close_time,
            is_open=False,
        )
