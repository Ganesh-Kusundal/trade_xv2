"""Shared response and mapping helpers for broker adapters.

These helpers keep adapter mappers small and consistent without changing
runtime behavior.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date, datetime
from decimal import Decimal
from typing import Any


def response_data(response: Any, default: Any = None) -> Any:
    """Return the nested ``data`` payload when present."""
    if isinstance(response, Mapping):
        return response.get("data", default)
    return default


def list_data(response: Any) -> list[dict[str, Any]]:
    """Return API list payloads as a list of dictionaries."""
    data = response_data(response, [])
    return data if isinstance(data, list) else []


def decimal_value(value: Any, default: Decimal = Decimal("0")) -> Decimal:
    """Convert a nullable API value to Decimal."""
    if value in (None, ""):
        return default
    return Decimal(str(value))


def int_value(value: Any, default: int = 0) -> int:
    """Convert a nullable API value to int."""
    if value in (None, ""):
        return default
    return int(value)


def string_value(value: Any, default: str = "") -> str:
    """Convert a nullable API value to str."""
    if value in (None, ""):
        return default
    return str(value)


def first_present(mapping: Mapping[str, Any], *names: str, default: Any = None) -> Any:
    """Return the first non-empty value from a mapping."""
    for name in names:
        value = mapping.get(name)
        if value not in (None, ""):
            return value
    return default


def quote_payload_from_response(response: Any, security_id: str) -> Mapping[str, Any]:
    """Extract the per-security quote payload from Dhan market-feed responses."""
    data = response_data(response, {})
    if isinstance(data, Mapping):
        for segment_data in data.values():
            if isinstance(segment_data, Mapping) and security_id in segment_data:
                value = segment_data[security_id]
                if isinstance(value, Mapping):
                    return value
    if isinstance(data, Mapping) and security_id in data:
        value = data[security_id]
        if isinstance(value, Mapping):
            return value
    if isinstance(data, Mapping) and any(
        key in data for key in ("last_price", "ltp", "open", "high", "low", "close")
    ):
        return data
    return {}


def candles_from_columns(
    response: Any,
    *,
    timestamp_factory: Any = datetime.now,
) -> list[Any]:
    """Build candle dictionaries from Dhan column-array historical responses."""
    data = response_data(response, {})
    has_column_payload = isinstance(response, Mapping) and any(
        key in response for key in ("timestamp", "open", "close")
    )
    if not isinstance(data, Mapping) or (not data and has_column_payload):
        data = response if isinstance(response, Mapping) else {}

    timestamps = data.get("timestamp", [])
    opens = data.get("open", [])
    highs = data.get("high", [])
    lows = data.get("low", [])
    closes = data.get("close", [])
    volumes = data.get("volume", [])

    candles: list[dict[str, Any]] = []
    for index in range(min(len(timestamps), len(closes))):
        raw_ts = timestamps[index] if index < len(timestamps) else None
        ts_value = _normalise_timestamp(raw_ts)
        candles.append(
            {
                "timestamp": _call_timestamp_factory(timestamp_factory, ts_value),
                "open": decimal_value(opens[index] if index < len(opens) else 0),
                "high": decimal_value(highs[index] if index < len(highs) else 0),
                "low": decimal_value(lows[index] if index < len(lows) else 0),
                "close": decimal_value(closes[index] if index < len(closes) else 0),
                "volume": int_value(volumes[index] if index < len(volumes) else 0),
            }
        )
    return candles


def option_contract_entries(response: Any) -> Sequence[Mapping[str, Any]]:
    """Return option-chain entries from Dhan responses."""
    data = response_data(response, {})
    if not isinstance(data, Mapping):
        return []
    oc_data = data.get("oc", [])
    return oc_data if isinstance(oc_data, list) else []


def _call_timestamp_factory(timestamp_factory: Any, value: Any) -> Any:
    try:
        return timestamp_factory(value)
    except TypeError:
        return timestamp_factory()


def _normalise_timestamp(value: Any) -> Any:
    if isinstance(value, int | float) and value > 10_000_000_000:
        return value / 1000.0
    if isinstance(value, int | float):
        return value
    return None


def timestamp_from_value(value: Any, fallback: Any = None) -> Any:
    """Convert numeric or ISO-like values into datetime/date objects."""
    if value is None:
        return fallback
    if isinstance(value, int | float):
        seconds = value / 1000.0 if value > 10_000_000_000 else float(value)
        return datetime.fromtimestamp(seconds)
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return fallback
    return value


def decimal_field(
    mapping: Mapping[str, Any], *names: str, default: Decimal = Decimal("0")
) -> Decimal:
    """Read the first Decimal field from a mapping."""
    return decimal_value(first_present(mapping, *names, default=default), default=default)


def int_field(mapping: Mapping[str, Any], *names: str, default: int = 0) -> int:
    """Read the first int field from a mapping."""
    return int_value(first_present(mapping, *names, default=default), default=default)


def str_field(mapping: Mapping[str, Any], *names: str, default: str = "") -> str:
    """Read the first string field from a mapping."""
    return string_value(first_present(mapping, *names, default=default), default=default)


def date_from_value(value: Any, fallback: date = date.today()) -> date:
    """Convert a value to date when possible."""
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, int | float):
        return date.fromtimestamp(value / 1000.0 if value > 10_000_000_000 else float(value))
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value).date()
        except ValueError:
            return fallback
    return fallback
