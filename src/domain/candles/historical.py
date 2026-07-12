"""Normalized historical bar models.

``HistoricalBar`` and ``HistoricalSeries`` are the canonical output types for
all historical data operations, whether fetched from a single broker or merged
across multiple sources by ``HistoricalDataCoordinator``.

Every bar carries ``DataProvenance`` so provenance survives federation and merge.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Any, Mapping

from domain.candles._helpers import (
    coerce_decimal,
    coerce_event_time,
    coverage_from_bars,
    find_timestamp_column,
    ohlcv_from_row,
    parse_broker_timestamp,
    parse_datalake_timestamp,
)
from domain.candles._indicators import SeriesIndicators
from domain.provenance import DataProvenance, ProvenanceConfidence


class BarLabelConvention(str, Enum):
    """Describes which edge of the bar interval the timestamp refers to."""

    LEFT = "LEFT"
    RIGHT = "RIGHT"
    CENTER = "CENTER"


@dataclass(frozen=True, slots=True)
class InstrumentRef:
    """Minimal instrument reference used in historical and streaming models."""

    symbol: str
    exchange: str

    def __str__(self) -> str:
        return f"{self.symbol}:{self.exchange}"


@dataclass(frozen=True)
class HistoricalBar:
    """A single normalized OHLCV bar."""

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
    close_time: datetime | None = None
    tick_count: int = 0
    extras: tuple[tuple[str, Any], ...] = ()

    @property
    def symbol(self) -> str:
        return self.instrument.symbol

    @property
    def exchange(self) -> str:
        return self.instrument.exchange

    @property
    def timestamp(self) -> datetime:
        return self.event_time

    @property
    def open_time(self) -> datetime:
        return self.event_time

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "symbol": self.symbol,
            "timestamp": self.timestamp,
            "open": float(self.open),
            "high": float(self.high),
            "low": float(self.low),
            "close": float(self.close),
            "volume": float(self.volume),
        }
        if self.extras:
            payload.update(dict(self.extras))
        return payload

    @classmethod
    def from_replay(
        cls,
        *,
        symbol: str,
        timestamp: datetime,
        open: Decimal | float | int | str,
        high: Decimal | float | int | str,
        low: Decimal | float | int | str,
        close: Decimal | float | int | str,
        volume: Decimal | float | int = 0,
        exchange: str = "NSE",
        timeframe: str = "1D",
        metadata: Mapping[str, Any] | None = None,
    ) -> HistoricalBar:
        event_time = coerce_event_time(timestamp)
        return cls(
            instrument=InstrumentRef(symbol=symbol, exchange=exchange),
            timeframe=timeframe,
            event_time=event_time,
            open=coerce_decimal(open),
            high=coerce_decimal(high),
            low=coerce_decimal(low),
            close=coerce_decimal(close),
            volume=int(volume),
            provenance=DataProvenance.now(
                broker_id="replay",
                request_id=f"replay:{symbol}:{timeframe}",
                confidence=ProvenanceConfidence.DERIVED,
                provider_timestamp=event_time,
                transformation_chain=("replay.bar",),
            ),
            extras=tuple(metadata.items()) if metadata else (),
        )

    @classmethod
    def from_live_bucket(
        cls,
        *,
        symbol: str,
        exchange: str,
        timeframe: str,
        open_time: datetime,
        close_time: datetime,
        open: float,
        high: float,
        low: float,
        close: float,
        volume: float,
        tick_count: int,
        broker_id: str = "stream",
        session_id: str = "",
    ) -> HistoricalBar:
        event_time = coerce_event_time(open_time)
        bucket_close = coerce_event_time(close_time)
        return cls(
            instrument=InstrumentRef(symbol=symbol, exchange=exchange),
            timeframe=timeframe,
            event_time=event_time,
            close_time=bucket_close,
            open=coerce_decimal(open),
            high=coerce_decimal(high),
            low=coerce_decimal(low),
            close=coerce_decimal(close),
            volume=int(volume),
            tick_count=tick_count,
            provenance=DataProvenance.now(
                broker_id=broker_id,
                request_id=f"agg:{session_id}:{symbol}:{timeframe}",
                confidence=ProvenanceConfidence.DERIVED,
                connection_id=session_id or None,
                provider_timestamp=event_time,
                transformation_chain=("stream.tick", "aggregate.ohlcv.v1"),
            ),
        )


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
    """A gap within a ``HistoricalSeries`` — a date range where bars are missing."""

    start: date
    end: date
    reason: str = "no_data"


@dataclass
class MergeManifest:
    """Audit record for a multi-source historical merge."""

    chunk_assignments: dict[str, str] = field(default_factory=dict)
    conflict_count: int = 0
    conflict_resolution: str = "prefer_primary"
    degraded: bool = False
    degraded_reason: str = ""


@dataclass
class HistoricalSeries:
    """Normalized collection of historical bars for a single instrument."""

    bars: list[HistoricalBar]
    coverage: DateRange
    instrument: InstrumentRef
    timeframe: str
    gaps: list[Gap] = field(default_factory=list)
    merge_manifest: MergeManifest | None = None

    @property
    def is_complete(self) -> bool:
        return len(self.gaps) == 0

    @property
    def is_degraded(self) -> bool:
        return self.merge_manifest is not None and self.merge_manifest.degraded

    @property
    def bar_count(self) -> int:
        return len(self.bars)

    def brokers_contributing(self) -> set[str]:
        return {b.provenance.source.broker_id for b in self.bars}

    def to_dataframe(self):
        import pandas as pd

        records = []
        for bar in self.bars:
            records.append({
                "timestamp": bar.event_time,
                "open": float(bar.open),
                "high": float(bar.high),
                "low": float(bar.low),
                "close": float(bar.close),
                "volume": int(bar.volume),
                "oi": int(bar.open_interest),
                "symbol": bar.instrument.symbol,
                "exchange": bar.instrument.exchange,
                "timeframe": bar.timeframe,
            })
        return pd.DataFrame(records, columns=[
            "timestamp", "open", "high", "low", "close",
            "volume", "oi", "symbol", "exchange", "timeframe",
        ])

    @property
    def df(self):
        return self.to_dataframe()

    @property
    def candles(self) -> list[HistoricalBar]:
        return self.bars

    @property
    def last(self) -> HistoricalBar | None:
        return self.bars[-1] if self.bars else None

    @property
    def first(self) -> HistoricalBar | None:
        return self.bars[0] if self.bars else None

    def between(self, start, end) -> HistoricalSeries:
        lo = self._coerce_boundary(start, floor=True)
        hi = self._coerce_boundary(end, floor=False)
        kept = [b for b in self.bars if lo <= b.event_time <= hi]
        return HistoricalSeries(
            bars=kept, coverage=self.coverage, instrument=self.instrument,
            timeframe=self.timeframe, gaps=self.gaps, merge_manifest=self.merge_manifest,
        )

    def append(self, bar: HistoricalBar) -> HistoricalSeries:
        return HistoricalSeries(
            bars=[*self.bars, bar], coverage=self.coverage, instrument=self.instrument,
            timeframe=self.timeframe, gaps=self.gaps, merge_manifest=self.merge_manifest,
        )

    def merge(self, other: HistoricalSeries) -> HistoricalSeries:
        by_time: dict[datetime, HistoricalBar] = {b.event_time: b for b in self.bars}
        for b in other.bars:
            by_time[b.event_time] = b
        merged = sorted(by_time.values(), key=lambda b: b.event_time)
        return HistoricalSeries(
            bars=merged, coverage=self.coverage, instrument=self.instrument,
            timeframe=self.timeframe, gaps=self.gaps + other.gaps,
            merge_manifest=self.merge_manifest,
        )

    def statistics(self) -> dict:
        if not self.bars:
            return {"count": 0, "high": None, "low": None, "avg_volume": 0.0, "return_pct": None}
        highs = [float(b.high) for b in self.bars]
        lows = [float(b.low) for b in self.bars]
        volumes = [int(b.volume) for b in self.bars]
        first_close = float(self.bars[0].close)
        last_close = float(self.bars[-1].close)
        return_pct = (
            ((last_close - first_close) / first_close) * 100.0 if first_close else None
        )
        return {
            "count": len(self.bars),
            "high": max(highs),
            "low": min(lows),
            "avg_volume": sum(volumes) / len(volumes),
            "return_pct": return_pct,
        }

    def resample(self, target_timeframe: str) -> HistoricalSeries:
        import pandas as pd

        if not self.bars:
            return HistoricalSeries(
                bars=[], coverage=self.coverage, instrument=self.instrument,
                timeframe=target_timeframe, gaps=self.gaps, merge_manifest=self.merge_manifest,
            )

        df = self.to_dataframe().set_index("timestamp")
        df = df.sort_index()
        rule = self._pandas_rule(target_timeframe)
        agg = df.resample(rule).agg({
            "open": "first", "high": "max", "low": "min",
            "close": "last", "volume": "sum", "oi": "last",
        }).dropna(subset=["close"])

        base_prov = self.bars[0].provenance.with_transformation(f"resample.{target_timeframe}")
        derived = DataProvenance(
            source=base_prov.source, fetched_at=base_prov.fetched_at,
            request_id=base_prov.request_id, confidence=ProvenanceConfidence.DERIVED,
            provider_timestamp=base_prov.provider_timestamp,
            transformation_chain=base_prov.transformation_chain,
        )

        new_bars: list[HistoricalBar] = []
        for ts, row in agg.iterrows():
            new_bars.append(HistoricalBar(
                instrument=self.instrument, timeframe=target_timeframe,
                event_time=pd.Timestamp(ts).to_pydatetime().replace(tzinfo=timezone.utc),
                open=Decimal(str(row["open"])), high=Decimal(str(row["high"])),
                low=Decimal(str(row["low"])), close=Decimal(str(row["close"])),
                volume=int(row["volume"]), provenance=derived,
                open_interest=int(row.get("oi", 0) or 0),
            ))
        return HistoricalSeries(
            bars=new_bars, coverage=self.coverage, instrument=self.instrument,
            timeframe=target_timeframe, gaps=self.gaps, merge_manifest=self.merge_manifest,
        )

    def export(self, format: str = "csv") -> str:
        df = self.to_dataframe()
        fmt = format.lower()
        if fmt == "csv":
            return df.to_csv(index=False)
        if fmt == "json":
            return df.to_json(orient="records", date_format="iso")
        raise ValueError(f"Unsupported export format: {format!r} (use 'csv' or 'json')")

    def indicators(self) -> SeriesIndicators:
        return SeriesIndicators(self)

    # ── Constructors (delegated to _constructors module) ───────────────

    @classmethod
    def from_broker_df(cls, df, instrument, timeframe, *, broker_id, request_id,
                       transformation_chain=("market_data.history", "normalize.ohlcv.v1")):
        from domain.candles._constructors import from_broker_df
        return from_broker_df(cls, df, instrument, timeframe,
                              broker_id=broker_id, request_id=request_id,
                              transformation_chain=transformation_chain)

    @classmethod
    def from_datalake_df(cls, df, instrument, timeframe, *, request_id="datalake"):
        from domain.candles._constructors import from_datalake_df
        return from_datalake_df(cls, df, instrument, timeframe, request_id=request_id)

    @classmethod
    def from_dataframe(cls, df, instrument, timeframe):
        from domain.candles._constructors import from_dataframe
        return from_dataframe(cls, df, instrument, timeframe)

    @staticmethod
    def _coerce_boundary(value, *, floor: bool) -> datetime:
        if isinstance(value, datetime):
            return value
        if isinstance(value, date):
            dt = datetime(value.year, value.month, value.day, tzinfo=timezone.utc)
            return dt if floor else dt.replace(hour=23, minute=59, second=59)
        if isinstance(value, str):
            parsed = datetime.fromisoformat(value)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed
        raise TypeError(f"Cannot coerce {type(value).__name__} to a boundary")

    @staticmethod
    def _pandas_rule(timeframe: str) -> str:
        tf = timeframe.strip().lower()
        if tf.endswith("m") and not tf.endswith("min"):
            return tf[:-1] + "min"
        return tf
