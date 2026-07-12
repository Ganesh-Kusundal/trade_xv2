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
from zoneinfo import ZoneInfo

from domain.provenance import DataProvenance, ProvenanceConfidence

_IST = ZoneInfo("Asia/Kolkata")
_TIMESTAMP_COLUMNS = ("timestamp", "date", "datetime", "time")


def _coerce_decimal(value: Decimal | float | int | str) -> Decimal:
    return value if isinstance(value, Decimal) else Decimal(str(value))


def _coerce_event_time(ts: datetime) -> datetime:
    if ts.tzinfo is None:
        return ts.replace(tzinfo=timezone.utc)
    return ts


def _find_timestamp_column(columns) -> str:
    for candidate in _TIMESTAMP_COLUMNS:
        if candidate in columns:
            return candidate
    raise ValueError(
        f"DataFrame missing timestamp column (expected one of {_TIMESTAMP_COLUMNS})"
    )


def _parse_broker_timestamp(value: object) -> datetime:
    import pandas as pd

    ts = value if isinstance(value, datetime) else pd.Timestamp(value).to_pydatetime()
    if ts.tzinfo is None:
        return ts.replace(tzinfo=timezone.utc)
    return ts.astimezone(timezone.utc)


def _parse_datalake_timestamp(value: object) -> datetime:
    """Parquet lake stores naive IST; convert to UTC for domain ``event_time``."""
    import pandas as pd

    ts = value if isinstance(value, datetime) else pd.Timestamp(value).to_pydatetime()
    if ts.tzinfo is None:
        local = ts.replace(tzinfo=_IST)
    else:
        local = ts.astimezone(_IST)
    return local.astimezone(timezone.utc)


def _ohlcv_from_row(row) -> tuple[Decimal, Decimal, Decimal, Decimal, int, int]:
    """Extract OHLCV from a DataFrame row; reject NaN/missing OHLC."""
    import pandas as pd

    def _cell(*keys: str):
        for key in keys:
            if key not in row:
                continue
            val = row[key]
            if val is not None and not (isinstance(val, float) and pd.isna(val)):
                return val
        raise ValueError("NaN or missing OHLCV field in historical row")

    open_val = _cell("open", "Open")
    high_val = _cell("high", "High")
    low_val = _cell("low", "Low")
    close_val = _cell("close", "Close")
    volume_val = _cell("volume", "Volume")
    oi_raw = row.get("oi", row.get("open_interest", 0))
    if oi_raw is None or (isinstance(oi_raw, float) and pd.isna(oi_raw)):
        oi_raw = 0
    return (
        _coerce_decimal(open_val),
        _coerce_decimal(high_val),
        _coerce_decimal(low_val),
        _coerce_decimal(close_val),
        int(volume_val or 0),
        int(oi_raw or 0),
    )


def _coverage_from_bars(bars: list[HistoricalBar]) -> DateRange:
    if bars:
        return DateRange(bars[0].event_time.date(), bars[-1].event_time.date())
    return DateRange(date.today(), date.today())


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
    close_time: datetime | None = None
    tick_count: int = 0
    extras: tuple[tuple[str, Any], ...] = ()

    # -- replay / streaming compatibility (symbol + timestamp aliases) ---------

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
        """Dict view for legacy strategy ``on_bar()`` hooks."""
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
        """Build a bar for replay / paper engines from OHLCV scalars."""
        event_time = _coerce_event_time(timestamp)
        return cls(
            instrument=InstrumentRef(symbol=symbol, exchange=exchange),
            timeframe=timeframe,
            event_time=event_time,
            open=_coerce_decimal(open),
            high=_coerce_decimal(high),
            low=_coerce_decimal(low),
            close=_coerce_decimal(close),
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
        """Build a closed live candle from an aggregator bucket."""
        event_time = _coerce_event_time(open_time)
        bucket_close = _coerce_event_time(close_time)
        return cls(
            instrument=InstrumentRef(symbol=symbol, exchange=exchange),
            timeframe=timeframe,
            event_time=event_time,
            close_time=bucket_close,
            open=_coerce_decimal(open),
            high=_coerce_decimal(high),
            low=_coerce_decimal(low),
            close=_coerce_decimal(close),
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

    def to_dataframe(self):
        """Convert this series to a canonical pandas DataFrame (lazy import)."""
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
            "timestamp",
            "open",
            "high",
            "low",
            "close",
            "volume",
            "oi",
            "symbol",
            "exchange",
            "timeframe",
        ])

    # ------------------------------------------------------------------
    # Convenience accessors (DataFrame becomes an *export* format only).
    # ------------------------------------------------------------------
    @property
    def df(self):
        """Alias for :meth:`to_dataframe` — the canonical export view."""
        return self.to_dataframe()

    @property
    def candles(self) -> list[HistoricalBar]:
        """Alias for :attr:`bars`."""
        return self.bars

    @property
    def last(self) -> HistoricalBar | None:
        """The most recent bar, or ``None`` if the series is empty."""
        return self.bars[-1] if self.bars else None

    @property
    def first(self) -> HistoricalBar | None:
        """The earliest bar, or ``None`` if the series is empty."""
        return self.bars[0] if self.bars else None

    # ------------------------------------------------------------------
    # Immutability-preserving transformations.
    # ------------------------------------------------------------------
    def between(self, start, end) -> HistoricalSeries:
        """Return a new series containing only bars within ``[start, end]``.

        ``start`` / ``end`` may be a ``datetime``, ``date`` (inclusive, expanded
        to the full day in UTC), or an ISO-8601 ``str``.
        """
        lo = self._coerce_boundary(start, floor=True)
        hi = self._coerce_boundary(end, floor=False)
        kept = [b for b in self.bars if lo <= b.event_time <= hi]
        return HistoricalSeries(
            bars=kept,
            coverage=self.coverage,
            instrument=self.instrument,
            timeframe=self.timeframe,
            gaps=self.gaps,
            merge_manifest=self.merge_manifest,
        )

    def append(self, bar: HistoricalBar) -> HistoricalSeries:
        """Return a new series with ``bar`` appended (input is unchanged)."""
        return HistoricalSeries(
            bars=[*self.bars, bar],
            coverage=self.coverage,
            instrument=self.instrument,
            timeframe=self.timeframe,
            gaps=self.gaps,
            merge_manifest=self.merge_manifest,
        )

    def merge(self, other: HistoricalSeries) -> HistoricalSeries:
        """Return a new series combining bars from both series.

        Bars are de-duplicated by ``event_time``; on collision the bar from
        ``other`` wins (newer-wins). Provenance/coverage come from ``self``.
        """
        by_time: dict[datetime, HistoricalBar] = {b.event_time: b for b in self.bars}
        for b in other.bars:
            by_time[b.event_time] = b
        merged = sorted(by_time.values(), key=lambda b: b.event_time)
        return HistoricalSeries(
            bars=merged,
            coverage=self.coverage,
            instrument=self.instrument,
            timeframe=self.timeframe,
            gaps=self.gaps + other.gaps,
            merge_manifest=self.merge_manifest,
        )

    # ------------------------------------------------------------------
    # Analytics.
    # ------------------------------------------------------------------
    def statistics(self) -> dict:
        """Return a small summary dict: count, high, low, avg_volume, return_pct."""
        if not self.bars:
            return {
                "count": 0,
                "high": None,
                "low": None,
                "avg_volume": 0.0,
                "return_pct": None,
            }
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
        """Resample to ``target_timeframe`` (e.g. ``"1D"``, ``"5m"``).

        Aggregation follows standard OHLCV rules: open=first, high=max,
        low=min, close=last, volume=sum. Produced bars are marked DERIVED.
        """
        import pandas as pd

        if not self.bars:
            return HistoricalSeries(
                bars=[],
                coverage=self.coverage,
                instrument=self.instrument,
                timeframe=target_timeframe,
                gaps=self.gaps,
                merge_manifest=self.merge_manifest,
            )

        df = self.to_dataframe().set_index("timestamp")
        df = df.sort_index()
        rule = self._pandas_rule(target_timeframe)
        agg = df.resample(rule).agg({
            "open": "first",
            "high": "max",
            "low": "min",
            "close": "last",
            "volume": "sum",
            "oi": "last",
        }).dropna(subset=["close"])

        base_prov = self.bars[0].provenance.with_transformation(
            f"resample.{target_timeframe}"
        )
        derived = DataProvenance(
            source=base_prov.source,
            fetched_at=base_prov.fetched_at,
            request_id=base_prov.request_id,
            confidence=ProvenanceConfidence.DERIVED,
            provider_timestamp=base_prov.provider_timestamp,
            transformation_chain=base_prov.transformation_chain,
        )

        new_bars: list[HistoricalBar] = []
        for ts, row in agg.iterrows():
            new_bars.append(HistoricalBar(
                instrument=self.instrument,
                timeframe=target_timeframe,
                event_time=pd.Timestamp(ts).to_pydatetime().replace(tzinfo=timezone.utc),
                open=Decimal(str(row["open"])),
                high=Decimal(str(row["high"])),
                low=Decimal(str(row["low"])),
                close=Decimal(str(row["close"])),
                volume=int(row["volume"]),
                provenance=derived,
                open_interest=int(row.get("oi", 0) or 0),
            ))
        return HistoricalSeries(
            bars=new_bars,
            coverage=self.coverage,
            instrument=self.instrument,
            timeframe=target_timeframe,
            gaps=self.gaps,
            merge_manifest=self.merge_manifest,
        )

    def export(self, format: str = "csv") -> str:
        """Export the series to a ``str`` in the given ``format``.

        Supported: ``"csv"`` (default) and ``"json"``.
        """
        df = self.to_dataframe()
        fmt = format.lower()
        if fmt == "csv":
            return df.to_csv(index=False)
        if fmt == "json":
            return df.to_json(orient="records", date_format="iso")
        raise ValueError(f"Unsupported export format: {format!r} (use 'csv' or 'json')")

    def indicators(self) -> SeriesIndicators:
        """Return a lightweight technical-indicator accessor for this series."""
        return SeriesIndicators(self)

    # ------------------------------------------------------------------
    # Constructors (single ingress family — ADR-020).
    # ------------------------------------------------------------------
    @classmethod
    def from_broker_df(
        cls,
        df: pd.DataFrame,  # noqa: F821
        instrument: InstrumentRef,
        timeframe: str,
        *,
        broker_id: str,
        request_id: str,
        transformation_chain: tuple[str, ...] = ("market_data.history", "normalize.ohlcv.v1"),
    ) -> HistoricalSeries:
        """Build a series from a broker-normalized OHLCV DataFrame (UTC ingress)."""
        if df is None or df.empty:
            return cls(
                bars=[],
                coverage=DateRange(date.today(), date.today()),
                instrument=instrument,
                timeframe=timeframe,
            )

        ts_col = _find_timestamp_column(df.columns)
        bars: list[HistoricalBar] = []
        for idx, row in df.iterrows():
            event_time = _parse_broker_timestamp(row[ts_col])
            open_d, high_d, low_d, close_d, volume, oi = _ohlcv_from_row(row)
            bars.append(
                HistoricalBar(
                    instrument=instrument,
                    timeframe=timeframe,
                    event_time=event_time,
                    open=open_d,
                    high=high_d,
                    low=low_d,
                    close=close_d,
                    volume=volume,
                    open_interest=oi,
                    bar_index=int(idx) if isinstance(idx, int) else len(bars),
                    provenance=DataProvenance.now(
                        broker_id=broker_id,
                        request_id=request_id,
                        provider_timestamp=event_time,
                        transformation_chain=transformation_chain,
                    ),
                    label_convention=BarLabelConvention.LEFT,
                )
            )
        bars.sort(key=lambda b: b.event_time)
        return cls(
            bars=bars,
            coverage=_coverage_from_bars(bars),
            instrument=instrument,
            timeframe=timeframe,
        )

    @classmethod
    def from_datalake_df(
        cls,
        df: pd.DataFrame,  # noqa: F821
        instrument: InstrumentRef,
        timeframe: str,
        *,
        request_id: str = "datalake",
    ) -> HistoricalSeries:
        """Build a series from datalake parquet (naive IST timestamps → UTC)."""
        if df is None or df.empty:
            return cls(
                bars=[],
                coverage=DateRange(date.today(), date.today()),
                instrument=instrument,
                timeframe=timeframe,
            )

        ts_col = _find_timestamp_column(df.columns)
        bars: list[HistoricalBar] = []
        for idx, row in df.iterrows():
            event_time = _parse_datalake_timestamp(row[ts_col])
            open_d, high_d, low_d, close_d, volume, oi = _ohlcv_from_row(row)
            bars.append(
                HistoricalBar(
                    instrument=instrument,
                    timeframe=timeframe,
                    event_time=event_time,
                    open=open_d,
                    high=high_d,
                    low=low_d,
                    close=close_d,
                    volume=volume,
                    open_interest=oi,
                    bar_index=int(idx) if isinstance(idx, int) else len(bars),
                    provenance=DataProvenance.now(
                        broker_id="datalake",
                        request_id=request_id,
                        confidence=ProvenanceConfidence.DERIVED,
                        provider_timestamp=event_time,
                        transformation_chain=("datalake.parquet", "normalize.ohlcv.ist_to_utc"),
                    ),
                    label_convention=BarLabelConvention.LEFT,
                )
            )
        bars.sort(key=lambda b: b.event_time)
        return cls(
            bars=bars,
            coverage=_coverage_from_bars(bars),
            instrument=instrument,
            timeframe=timeframe,
        )

    @classmethod
    def from_dataframe(
        cls,
        df: pd.DataFrame,  # noqa: F821
        instrument: InstrumentRef,
        timeframe: str,
    ) -> HistoricalSeries:
        """Replay/backtest ingress — delegates to :meth:`from_broker_df`."""
        return cls.from_broker_df(
            df,
            instrument,
            timeframe,
            broker_id="replay",
            request_id="from_dataframe",
            transformation_chain=("replay.bar",),
        )

    # ------------------------------------------------------------------
    # Internal helpers.
    # ------------------------------------------------------------------
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
        """Map our timeframe strings to pandas resample offset aliases."""
        tf = timeframe.strip().lower()
        if tf.endswith("m") and not tf.endswith("min"):
            return tf[:-1] + "min"
        return tf


class SeriesIndicators:
    """Lightweight technical-indicator accessor over a :class:`HistoricalSeries`.

    All methods return a pandas ``Series`` indexed by the series' ``event_time``,
    suitable for plotting or further arithmetic. Pure-function: no state is
    mutated on the underlying series.
    """

    def __init__(self, series: HistoricalSeries) -> None:
        self._series = series

    def _close_series(self):
        import pandas as pd

        idx = [b.event_time for b in self._series.bars]
        vals = [float(b.close) for b in self._series.bars]
        return pd.Series(vals, index=pd.DatetimeIndex(idx, tz="UTC"), name="close")

    def sma(self, period: int) -> pd.Series:  # noqa: F821
        """Simple moving average of close over ``period`` bars."""
        s = self._close_series()
        return s.rolling(window=period, min_periods=period).mean().rename(f"sma_{period}")

    def ema(self, period: int) -> pd.Series:  # noqa: F821
        """Exponential moving average of close over ``period`` bars."""
        s = self._close_series()
        return s.ewm(span=period, adjust=False).mean().rename(f"ema_{period}")

    def rsi(self, period: int = 14) -> pd.Series:  # noqa: F821
        """Relative Strength Index of close (Wilder-style smoothing)."""
        import pandas as pd

        s = self._close_series()
        delta = s.diff()
        gain = delta.clip(lower=0)
        loss = -delta.clip(upper=0)
        avg_gain = gain.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
        avg_loss = loss.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
        rs = avg_gain / avg_loss.replace(0, pd.NA)
        rsi = 100 - (100 / (1 + rs))
        return rsi.rename(f"rsi_{period}")

    def patterns(self) -> pd.DataFrame:  # noqa: F821
        """Candlestick + swing pattern columns for this series.

        Returns a DataFrame indexed by ``event_time`` with the same columns as
        :class:`domain.indicators.patterns.CandlestickPatterns` (boolean flags
        plus the ``cdl_direction`` enum). Mirrors ``rsi()`` accessor style.
        """
        import pandas as pd

        from domain.indicators.patterns import CandlestickPatterns

        idx = [b.event_time for b in self._series.bars]
        df = pd.DataFrame({
            "open": [float(b.open) for b in self._series.bars],
            "high": [float(b.high) for b in self._series.bars],
            "low": [float(b.low) for b in self._series.bars],
            "close": [float(b.close) for b in self._series.bars],
            "volume": [float(b.volume) for b in self._series.bars],
        })
        out = CandlestickPatterns().compute(df)
        out.index = pd.DatetimeIndex(idx, tz="UTC")
        return out
