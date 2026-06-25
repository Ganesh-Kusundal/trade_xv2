"""Normalized historical bar models.

``HistoricalBar`` and ``HistoricalSeries`` are the canonical output types for
all historical data operations, whether fetched from a single broker or merged
across multiple sources by ``HistoricalDataCoordinator``.

Every bar carries ``DataProvenance`` so provenance survives federation and merge.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from enum import Enum

from domain.provenance import DataProvenance


class BarLabelConvention(str, Enum):
    """Describes which edge of the bar interval the timestamp refers to.

    LEFT   — timestamp is the bar *open* time (most common, e.g. Upstox).
    RIGHT  — timestamp is the bar *close* time (some broker responses).
    CENTER — timestamp is the midpoint (unusual; flag explicitly).
    """

    LEFT = "LEFT"
    RIGHT = "RIGHT"
    CENTER = "CENTER"


@dataclass(frozen=True, slots=True)
class InstrumentRef:
    """Minimal instrument reference used in historical and streaming models.

    symbol   — canonical ticker symbol, e.g. ``"RELIANCE"``.
    exchange — exchange string, e.g. ``"NSE"``, ``"BSE"``, ``"NFO"``.
    """

    symbol: str
    exchange: str

    def __str__(self) -> str:
        return f"{self.symbol}:{self.exchange}"


@dataclass(frozen=True)
class HistoricalBar:
    """A single normalized OHLCV bar.

    Fields
    ------
    instrument      — the instrument this bar belongs to.
    timeframe       — candle interval, e.g. ``"1m"``, ``"5m"``, ``"1D"``.
    event_time      — bar open time (UTC, timezone-aware). This is the canonical
                      timestamp regardless of the broker's label convention.
    open / high / low / close / volume — OHLCV data.
    open_interest   — optional OI for derivatives.
    bar_index       — zero-based position in the series (set by coordinator).
    is_partial      — True for the last bar in a live response (incomplete candle).
    label_convention — whether the raw broker timestamp was LEFT or RIGHT; stored
                       for audit purposes even after normalization.
    provenance      — full data lineage.
    """

    instrument: InstrumentRef
    timeframe: str
    event_time: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: int
    provenance: DataProvenance
    open_interest: int = 0
    bar_index: int = 0
    is_partial: bool = False
    label_convention: BarLabelConvention = BarLabelConvention.LEFT


@dataclass(frozen=False)
class DateRange:
    """An inclusive date range."""

    start: date
    end: date

    def days(self) -> int:
        return (self.end - self.start).days + 1

    def __contains__(self, d: date) -> bool:
        return self.start <= d <= self.end


@dataclass(frozen=True)
class Gap:
    """A gap within a ``HistoricalSeries`` — a date range where bars are missing.

    reason may be: ``"broker_error"``, ``"quota_exhausted"``, ``"no_data"``
    (holidays / non-trading days), ``"range_exceeded"``.
    """

    start: date
    end: date
    reason: str = "no_data"


@dataclass
class MergeManifest:
    """Audit record for a multi-source historical merge.

    chunk_assignments maps chunk_id → broker_id for each fetched chunk.
    conflict_count    — number of bars with differing OHLCV across sources.
    conflict_resolution — strategy used: ``"prefer_primary"``, ``"prefer_newest"``,
                          ``"fail_on_conflict"``.
    """

    chunk_assignments: dict[str, str] = field(default_factory=dict)
    conflict_count: int = 0
    conflict_resolution: str = "prefer_primary"
    degraded: bool = False
    degraded_reason: str = ""


@dataclass
class HistoricalSeries:
    """Normalized collection of historical bars for a single instrument.

    bars         — sequence of bars ordered by ``event_time`` ascending.
    coverage     — date range that was *requested* (not necessarily fully filled).
    gaps         — explicit gaps within the coverage range.
    merge_manifest — populated when bars come from multiple brokers; None for
                     single-source fetches.
    """

    bars: list[HistoricalBar]
    coverage: DateRange
    instrument: InstrumentRef
    timeframe: str
    gaps: list[Gap] = field(default_factory=list)
    merge_manifest: MergeManifest | None = None

    @property
    def is_complete(self) -> bool:
        """True when there are no registered gaps."""
        return len(self.gaps) == 0

    @property
    def is_degraded(self) -> bool:
        """True when the merge manifest signals degraded mode."""
        return self.merge_manifest is not None and self.merge_manifest.degraded

    @property
    def bar_count(self) -> int:
        return len(self.bars)

    def brokers_contributing(self) -> set[str]:
        """Return the set of broker_ids that contributed bars."""
        return {b.provenance.source.broker_id for b in self.bars}
