"""Normalized options historical bar models."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import TYPE_CHECKING, Literal

from domain.parsing import require_tz_aware

if TYPE_CHECKING:
    import pandas as pd

ExpiryKind = Literal["WEEK", "MONTH"]
OptionSide = Literal["CALL", "PUT"]

DEFAULT_STRIKE_OFFSETS: tuple[int, ...] = tuple(range(-10, 11))
DEFAULT_OPTION_TYPES: tuple[OptionSide, ...] = ("CALL", "PUT")

OPTIONS_CANONICAL_COLUMNS: tuple[str, ...] = (
    "timestamp",
    "symbol",
    "underlying",
    "exchange",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "oi",
    "iv",
    "spot",
    "strike",
    "strike_offset",
    "option_type",
    "expiry_kind",
    "expiry_code",
    "interval_min",
    "expiry_date",
)


@dataclass(frozen=True, slots=True)
class OptionsHistoricalQuery:
    """Query for rolling options historical bars (lake partition dimensions)."""

    underlying: str
    expiry_kind: ExpiryKind
    expiry_code: int
    from_date: date
    to_date: date
    interval_min: int = 5
    strike_offsets: tuple[int, ...] = DEFAULT_STRIKE_OFFSETS
    option_types: tuple[OptionSide, ...] = DEFAULT_OPTION_TYPES
    request_id: str | None = None


@dataclass(frozen=True, slots=True)
class OptionsBar:
    """One normalized options OHLCV bar."""

    timestamp: datetime
    symbol: str
    underlying: str
    exchange: str
    open: float
    high: float
    low: float
    close: float
    volume: int
    oi: int
    iv: float
    spot: float
    strike: float
    strike_offset: int
    option_type: OptionSide
    expiry_kind: ExpiryKind
    expiry_code: int
    interval_min: int
    expiry_date: str

    def __post_init__(self) -> None:
        require_tz_aware(
            self.timestamp,
            f"OptionsBar.timestamp must be timezone-aware, got naive {self.timestamp!r}",
        )


@dataclass
class OptionsHistoricalSeries:
    """Merged options bars for one lake partition group."""

    query: OptionsHistoricalQuery
    bars: list[OptionsBar] = field(default_factory=list)

    def to_dataframe(self) -> "pd.DataFrame":
        import pandas as pd

        if not self.bars:
            return pd.DataFrame(columns=list(OPTIONS_CANONICAL_COLUMNS))
        rows = [
            {
                "timestamp": b.timestamp,
                "symbol": b.symbol,
                "underlying": b.underlying,
                "exchange": b.exchange,
                "open": b.open,
                "high": b.high,
                "low": b.low,
                "close": b.close,
                "volume": b.volume,
                "oi": b.oi,
                "iv": b.iv,
                "spot": b.spot,
                "strike": b.strike,
                "strike_offset": b.strike_offset,
                "option_type": b.option_type,
                "expiry_kind": b.expiry_kind,
                "expiry_code": b.expiry_code,
                "interval_min": b.interval_min,
                "expiry_date": b.expiry_date,
            }
            for b in self.bars
        ]
        df = pd.DataFrame(rows)
        return df[[c for c in OPTIONS_CANONICAL_COLUMNS if c in df.columns]]
