"""Domain ingress: broker vs datalake timezone and NaN rejection."""

from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

from domain.candles.historical import HistoricalSeries, InstrumentRef
from interface.api.candle_mapper import series_to_api_candles

_INSTRUMENT = InstrumentRef(symbol="RELIANCE", exchange="NSE")
_IST = ZoneInfo("Asia/Kolkata")


def test_from_datalake_df_ist_naive_to_utc() -> None:
    """Lake parquet naive IST must become UTC event_time (not relabel as UTC)."""
    local_open = datetime(2026, 1, 2, 9, 15)  # naive IST wall clock
    df = pd.DataFrame(
        {
            "timestamp": [local_open],
            "open": [100.0],
            "high": [101.0],
            "low": [99.0],
            "close": [100.5],
            "volume": [1000],
            "oi": [0],
        }
    )
    series = HistoricalSeries.from_datalake_df(df, _INSTRUMENT, "1m")
    bar = series.bars[0]
    expected_utc = local_open.replace(tzinfo=_IST).astimezone(timezone.utc)
    assert bar.event_time == expected_utc
    assert bar.provenance.source.broker_id == "datalake"


def test_from_broker_df_naive_assumes_utc() -> None:
    ts = datetime(2026, 1, 2, 9, 15, tzinfo=timezone.utc)
    df = pd.DataFrame(
        {
            "timestamp": [ts.replace(tzinfo=None)],
            "open": [100.0],
            "high": [101.0],
            "low": [99.0],
            "close": [100.5],
            "volume": [1000],
        }
    )
    series = HistoricalSeries.from_broker_df(
        df, _INSTRUMENT, "1m", broker_id="dhan", request_id="test"
    )
    assert series.bars[0].event_time == ts


def test_from_datalake_df_rejects_nan_ohlc() -> None:
    df = pd.DataFrame(
        {
            "timestamp": [datetime(2026, 1, 2, 9, 15)],
            "open": [float("nan")],
            "high": [101.0],
            "low": [99.0],
            "close": [100.5],
            "volume": [1000],
        }
    )
    with pytest.raises(ValueError, match="NaN or missing OHLCV"):
        HistoricalSeries.from_datalake_df(df, _INSTRUMENT, "1m")


def test_series_to_api_candles_roundtrip_ms() -> None:
    local_open = datetime(2026, 1, 2, 9, 15)
    df = pd.DataFrame(
        {
            "timestamp": [local_open],
            "open": [100.0],
            "high": [101.0],
            "low": [99.0],
            "close": [100.5],
            "volume": [1000],
            "oi": [0],
        }
    )
    series = HistoricalSeries.from_datalake_df(df, _INSTRUMENT, "1D")
    candles = series_to_api_candles(series)
    assert len(candles) == 1
    assert candles[0].o == 100.0
    assert candles[0].c == 100.5
    expected_ms = int(series.bars[0].event_time.timestamp() * 1000)
    assert candles[0].t == expected_ms
