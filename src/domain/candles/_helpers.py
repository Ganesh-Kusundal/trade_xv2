"""Helper functions for historical bar models."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import TYPE_CHECKING

from domain.constants.market import IST as _IST

if TYPE_CHECKING:
    from domain.candles.historical import DateRange

_TIMESTAMP_COLUMNS = ("timestamp", "date", "datetime", "time")


def coerce_decimal(value: Decimal | float | int | str) -> Decimal:
    return value if isinstance(value, Decimal) else Decimal(str(value))


def coerce_event_time(ts: datetime) -> datetime:
    if ts.tzinfo is None:
        return ts.replace(tzinfo=timezone.utc)
    return ts


def find_timestamp_column(columns) -> str:
    for candidate in _TIMESTAMP_COLUMNS:
        if candidate in columns:
            return candidate
    raise ValueError(
        f"DataFrame missing timestamp column (expected one of {_TIMESTAMP_COLUMNS})"
    )


def parse_broker_timestamp(value: object) -> datetime:
    import pandas as pd

    ts = value if isinstance(value, datetime) else pd.Timestamp(value).to_pydatetime()
    if ts.tzinfo is None:
        return ts.replace(tzinfo=timezone.utc)
    return ts.astimezone(timezone.utc)


def parse_datalake_timestamp(value: object) -> datetime:
    """Parquet lake stores naive IST; convert to UTC for domain ``event_time``."""
    import pandas as pd

    ts = value if isinstance(value, datetime) else pd.Timestamp(value).to_pydatetime()
    if ts.tzinfo is None:
        local = ts.replace(tzinfo=_IST)
    else:
        local = ts.astimezone(_IST)
    return local.astimezone(timezone.utc)


def ohlcv_from_row(row) -> tuple[Decimal, Decimal, Decimal, Decimal, int, int]:
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
        coerce_decimal(open_val),
        coerce_decimal(high_val),
        coerce_decimal(low_val),
        coerce_decimal(close_val),
        int(volume_val or 0),
        int(oi_raw or 0),
    )


def coverage_from_bars(bars: list) -> "DateRange":
    from domain.candles.historical import DateRange

    if bars:
        return DateRange(bars[0].event_time.date(), bars[-1].event_time.date())
    return DateRange(datetime.now().date(), datetime.now().date())
