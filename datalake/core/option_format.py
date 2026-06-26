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

_IST = timezone(timedelta(hours=5, minutes=30))


def make_option_symbol(
    underlying: str, expiry_kind: str, expiry_code: int, strike_offset: int, option_type: str
) -> str:
    """Build a canonical option symbol string.

    Example: ("NIFTY", "WEEK", 1, -2, "CALL") → "NIFTY_WEEK_1_-2_CALL"
    Also accepts CE/PE and normalizes to CALL/PUT.
    """
    # Normalize option type: CE→CALL, PE→PUT
    ot = option_type.upper().strip()
    if ot in ("CE", "CALL"):
        ot = "CALL"
    elif ot in ("PE", "PUT"):
        ot = "PUT"
    return f"{underlying}_{expiry_kind}_{int(expiry_code)}_{int(strike_offset)}_{ot}"


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
        .dt.tz_convert("Asia/Kolkata")
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
    out["exchange"] = "NSE"
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
    ref = datetime.fromtimestamp(reference_ts_ms / 1000, tz=timezone.utc).astimezone(_IST)

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
