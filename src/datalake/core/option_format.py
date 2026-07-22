"""Shared option data format helpers.

Single source of truth for converting Trade_J option format to TradeXV2 canonical.
Used by both `datalake/migrate_options.py` (one-time migration) and
`datalake/sync_options.py` (daily incremental sync).

Source format (Trade_J):
  - Prices in paise (÷100 for rupees)
  - Timestamps in epoch milliseconds (→ IST naive datetime)
  - Underlying: NIFTY, BANKNIFTY
  - Option type: CALL, PUT
  - Expiry code: sequential integer (1, 2, ...)

Target format (TradeXV2 canonical):
  - Prices in rupees (float64)
  - Timestamps: naive datetime in Asia/Kolkata
  - Symbol: f"{underlying}_{expiry_kind}_{expiry_code}_{strike_offset}_{option_type}"
  - Exchange: NSE
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pandas as pd

from domain.symbols import normalize_symbol

CANONICAL_COLUMNS: list[str] = [
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
]


def _get_exchange_tz() -> timezone:
    """Return the active exchange's timezone as a stdlib timezone."""
    from zoneinfo import ZoneInfo

    from datalake.exchange_registry import get_active_adapter

    tz_name = get_active_adapter().timezone
    return ZoneInfo(tz_name)


def _get_exchange_code() -> str:
    """Return the active exchange's canonical code (e.g. 'NSE')."""
    from datalake.exchange_registry import get_active_exchange_code

    return get_active_exchange_code()


def make_option_symbol(
    underlying: str, expiry_kind: str, expiry_code: int, strike_offset: int, option_type: str
) -> str:
    """Build a canonical option symbol string.

    Example: ("NIFTY", "WEEK", 1, -2, "CALL") → "NIFTY_WEEK_1_-2_CALL"
    Also accepts CE/PE and normalizes to CALL/PUT.
    """
    # Normalize option type: CE→CALL, PE→PUT
    ot = normalize_symbol(option_type)
    if ot in ("CE", "CALL"):
        ot = "CALL"
    elif ot in ("PE", "PUT"):
        ot = "PUT"
    return f"{underlying}_{expiry_kind}_{int(expiry_code)}_{int(strike_offset)}_{ot}"


def strike_offset_to_dhan_strike(offset: int) -> str:
    """Map lake strike_offset (-10..+10) to Dhan rolling API strike string."""
    if offset == 0:
        return "ATM"
    if offset > 0:
        return f"ATM+{offset}"
    return f"ATM{offset}"


def lake_to_dhan_expiry_code(lake_code: int) -> int:
    """Lake expiry_code 1/2 maps directly to Dhan rolling API (1=nearest, 2=next).

    Do not subtract 1 — Dhan rejects ``0`` (often omitted as falsy in payloads).
    """
    return int(lake_code)


def _parse_dhan_timestamps(values: list) -> pd.Series:
    s = pd.Series(values)
    if pd.api.types.is_numeric_dtype(s):
        mx = float(s.max()) if len(s) else 0.0
        unit = "ms" if mx > 1e12 else "s"
        ts = pd.to_datetime(s, unit=unit, utc=True)
    else:
        ts = pd.to_datetime(s, utc=True)
    return ts.dt.tz_convert(_get_exchange_tz()).dt.tz_localize(None)


def convert_from_dhan_rolling(
    side_data: dict,
    *,
    underlying: str,
    expiry_kind: str,
    expiry_code: int,
    strike_offset: int,
    option_type: str,
    interval_min: int = 5,
) -> pd.DataFrame:
    """Convert Dhan rolling-option CE/PE array payload to canonical rows."""
    if not side_data or not side_data.get("timestamp"):
        return pd.DataFrame(columns=CANONICAL_COLUMNS)

    n = len(side_data["timestamp"])
    timestamps = _parse_dhan_timestamps(side_data["timestamp"])

    def _col(name: str, default: float = 0.0) -> list:
        arr = side_data.get(name)
        if arr is None or len(arr) != n:
            return [default] * n
        return list(arr)

    ot = "CALL" if str(option_type).upper() in ("CALL", "CE") else "PUT"
    symbol = make_option_symbol(underlying, expiry_kind, expiry_code, strike_offset, ot)
    first_ts_ms = int(pd.Timestamp(timestamps.iloc[0]).timestamp() * 1000)
    expiry_date = map_expiry_code_to_date(underlying, expiry_kind, int(expiry_code), first_ts_ms)

    df = pd.DataFrame(
        {
            "timestamp": timestamps,
            "symbol": [symbol] * n,
            "underlying": underlying,
            "exchange": _get_exchange_code(),
            "open": _col("open"),
            "high": _col("high"),
            "low": _col("low"),
            "close": _col("close"),
            "volume": [int(x or 0) for x in _col("volume", 0.0)],
            "oi": [int(x or 0) for x in _col("oi", 0.0)],
            "iv": _col("iv", float("nan")),
            "spot": _col("spot"),
            "strike": _col("strike", float("nan")),
            "strike_offset": int(strike_offset),
            "option_type": ot,
            "expiry_kind": expiry_kind,
            "expiry_code": int(expiry_code),
            "interval_min": int(interval_min),
            "expiry_date": expiry_date,
        }
    )
    return df[[c for c in CANONICAL_COLUMNS if c in df.columns]]


def convert_format(raw: pd.DataFrame) -> pd.DataFrame:
    """Convert Trade_J format to TradeXV2 canonical.

    Transforms (in place on a copy):
      - bar_time_ms → timestamp (naive datetime in IST)
      - *_paisa → *_rupees (÷100)
      - Constructs `symbol` from underlying + expiry_kind + expiry_code + strike_offset + option_type
      - Sets exchange = "NSE"

    Returns a new DataFrame with canonical columns plus the original raw columns
    (so caller can still access bar_time_ms, ingested_at_ms etc.).
    """
    out = raw.copy()
    out["timestamp"] = (
        pd.to_datetime(out["bar_time_ms"], unit="ms", utc=True)
        .dt.tz_convert(_get_exchange_tz())
        .dt.tz_localize(None)
    )
    for src, dst in [
        ("open_paisa", "open"),
        ("high_paisa", "high"),
        ("low_paisa", "low"),
        ("close_paisa", "close"),
        ("spot_paisa", "spot"),
        ("strike_paisa", "strike"),
    ]:
        out[dst] = out[src] / 100.0
    out["symbol"] = [
        make_option_symbol(u, ek, ec, so, ot)
        for u, ek, ec, so, ot in zip(
            out["underlying"].astype(str),
            out["expiry_kind"].astype(str),
            out["expiry_code"],
            out["strike_offset"],
            out["option_type"].astype(str),
            strict=False,
        )
    ]
    out["exchange"] = _get_exchange_code()

    # Add canonical instrument_id column
    from datalake.core.symbols import instrument_id_from_option

    out["instrument_id"] = [
        instrument_id_from_option(u, exp, s, ot)
        for u, exp, s, ot in zip(
            out["underlying"].astype(str),
            out["expiry_date"].astype(str) if "expiry_date" in out.columns else [""] * len(out),
            out["strike"],
            out["option_type"].astype(str),
            strict=False,
        )
    ]

    return out


def map_expiry_code_to_date(
    underlying: str, expiry_kind: str, expiry_code: int, reference_ts_ms: int
) -> str:
    """Map (underlying, kind, code) to an ISO date string.

    Trade_J uses sequential codes (1, 2, ...) rather than actual dates.
    For NIFTY/BANKNIFTY, weekly expiry is every Thursday, monthly is last Thursday.
    Uses the first bar's timestamp as the reference.

    For WEEK code=1: nearest Thursday on or after reference
    For WEEK code=2: next Thursday after that
    For MONTH code=1: last Thursday of the month containing reference
    """
    ref = datetime.fromtimestamp(reference_ts_ms / 1000, tz=timezone.utc).astimezone(
        _get_exchange_tz()
    )

    if underlying not in ("NIFTY", "BANKNIFTY"):
        return ref.strftime("%Y-%m-%d")

    if expiry_kind == "WEEK":
        days_to_thursday = (3 - ref.weekday()) % 7
        if days_to_thursday == 0:
            days_to_thursday = 7
        base_thursday = ref + timedelta(days=days_to_thursday)
        if expiry_code == 1:
            return base_thursday.strftime("%Y-%m-%d")
        return (base_thursday + timedelta(days=7)).strftime("%Y-%m-%d")

    if expiry_kind == "MONTH":
        if ref.month == 12:
            next_month = ref.replace(year=ref.year + 1, month=1, day=1)
        else:
            next_month = ref.replace(month=ref.month + 1, day=1)
        last_day = next_month - timedelta(days=1)
        days_back = (last_day.weekday() - 3) % 7
        expiry_date = last_day - timedelta(days=days_back)
        return expiry_date.strftime("%Y-%m-%d")

    return ref.strftime("%Y-%m-%d")
