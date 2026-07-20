"""DataFrame → HistoricalSeries constructors (from_broker_df, from_datalake_df, from_dataframe)."""

from __future__ import annotations

from datetime import date

from domain.candles._helpers import (
    coverage_from_bars,
    find_timestamp_column,
    ohlcv_from_row,
    parse_broker_timestamp,
    parse_datalake_timestamp,
)
from domain.candles.historical import (
    BarLabelConvention,
    DateRange,
    HistoricalBar,
    HistoricalSeries,
    InstrumentRef,
)
from domain.provenance import DataProvenance, ProvenanceConfidence


def from_broker_df(
    cls,
    df,
    instrument: InstrumentRef,
    timeframe: str,
    *,
    broker_id: str,
    request_id: str,
    transformation_chain: tuple[str, ...] = ("market_data.history", "normalize.ohlcv.v1"),
) -> HistoricalSeries:
    """Build a series from a broker-normalized OHLCV DataFrame (UTC ingress)."""
    if df is None or df.empty:
        return HistoricalSeries(
            bars=[],
            coverage=DateRange(date.today(), date.today()),
            instrument=instrument,
            timeframe=timeframe,
        )

    ts_col = find_timestamp_column(df.columns)
    bars: list[HistoricalBar] = []
    for idx, row in df.iterrows():
        event_time = parse_broker_timestamp(row[ts_col])
        open_d, high_d, low_d, close_d, volume, oi = ohlcv_from_row(row)
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
    return HistoricalSeries(
        bars=bars,
        coverage=coverage_from_bars(bars),
        instrument=instrument,
        timeframe=timeframe,
    )


def from_datalake_df(
    cls,
    df,
    instrument: InstrumentRef,
    timeframe: str,
    *,
    request_id: str = "datalake",
) -> HistoricalSeries:
    """Build a series from datalake parquet (naive IST timestamps → UTC)."""
    if df is None or df.empty:
        return HistoricalSeries(
            bars=[],
            coverage=DateRange(date.today(), date.today()),
            instrument=instrument,
            timeframe=timeframe,
        )

    ts_col = find_timestamp_column(df.columns)
    bars: list[HistoricalBar] = []
    for idx, row in df.iterrows():
        event_time = parse_datalake_timestamp(row[ts_col])
        open_d, high_d, low_d, close_d, volume, oi = ohlcv_from_row(row)
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
    return HistoricalSeries(
        bars=bars,
        coverage=coverage_from_bars(bars),
        instrument=instrument,
        timeframe=timeframe,
    )


def from_dataframe(
    cls,
    df,
    instrument: InstrumentRef,
    timeframe: str,
) -> HistoricalSeries:
    """Replay/backtest ingress — delegates to from_broker_df."""
    return from_broker_df(
        cls,
        df,
        instrument,
        timeframe,
        broker_id="replay",
        request_id="from_dataframe",
        transformation_chain=("replay.bar",),
    )
