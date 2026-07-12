"""Map domain OHLCV bars to API wire schemas."""

from __future__ import annotations

from domain.candles.historical import HistoricalBar, HistoricalSeries
from interface.api.schemas import Candle


def api_candle_from_bar(bar: HistoricalBar) -> Candle:
    """Convert a canonical :class:`HistoricalBar` to the REST ``Candle`` schema."""
    ts_ms = int(bar.event_time.timestamp() * 1000)
    return Candle(
        t=ts_ms,
        o=float(bar.open),
        h=float(bar.high),
        l=float(bar.low),
        c=float(bar.close),
        v=float(bar.volume),
        oi=float(bar.open_interest),
    )


def series_to_api_candles(
    series: HistoricalSeries,
    *,
    limit: int | None = None,
) -> list[Candle]:
    """Map a domain series to REST wire candles (single API egress — ADR-020)."""
    bars = series.bars[-limit:] if limit else series.bars
    return [api_candle_from_bar(bar) for bar in bars]
