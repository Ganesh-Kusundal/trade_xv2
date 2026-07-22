"""Broker-agnostic exchange/event time extraction from quote payloads."""

from __future__ import annotations

from datetime import datetime
from typing import Any

_QUOTE_TIME_KEYS = ("timestamp", "last_traded_time", "exchange_timestamp", "LTT")


def _coerce_timestamp(ts_raw: Any, tz_default: datetime) -> datetime | None:
    if ts_raw is None or ts_raw == "":
        return None
    if isinstance(ts_raw, datetime):
        return ts_raw if ts_raw.tzinfo else ts_raw.replace(tzinfo=tz_default.tzinfo)
    try:
        if isinstance(ts_raw, int | float):
            if ts_raw <= 0:
                return None
            if ts_raw > 1e11:
                return datetime.fromtimestamp(ts_raw / 1000, tz=tz_default.tzinfo)
            return datetime.fromtimestamp(ts_raw, tz=tz_default.tzinfo)
        if isinstance(ts_raw, str) and ts_raw.strip():
            parsed = datetime.fromisoformat(ts_raw)
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=tz_default.tzinfo)
    except (ValueError, OSError, OverflowError):
        return None
    return None


def parse_quote_exchange_time(data: Any, tz_default: datetime) -> datetime | None:
    """Extract broker-reported exchange/event time from a quote payload."""
    if isinstance(data, dict):
        for key in _QUOTE_TIME_KEYS:
            parsed = _coerce_timestamp(data.get(key), tz_default)
            if parsed is not None:
                return parsed
        return None

    ts_raw = getattr(data, "timestamp", None)
    if ts_raw is not None and ts_raw != "":
        return _coerce_timestamp(ts_raw, tz_default)
    return None
