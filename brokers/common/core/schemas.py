"""DEPRECATED: This module is no longer used. Kept for backward compatibility only.

Canonical DataFrame schemas have been superseded by domain dataclasses in
brokers.common.core.domain. No module in the codebase imports this file.

The Broker ABC has been replaced by broker-specific gateway classes:
- Dhan: brokers.dhan.gateway.BrokerGateway
- Paper: brokers.paper.PaperGateway
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

import pandas as pd
from pandas import DataFrame

# ── Schema column definitions ──────────────────────────────────────────────


class HistoricalSchema:
    """Historical OHLCV candle schema."""

    COLUMNS: list[str] = [
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
    ]

    COLUMN_TYPES: dict[str, str] = {
        "timestamp": "datetime64[ns, UTC]",
        "open": "float64",
        "high": "float64",
        "low": "float64",
        "close": "float64",
        "volume": "int64",
        "oi": "int64",
        "symbol": "string",
        "exchange": "string",
        "timeframe": "string",
    }

    @classmethod
    def validate(cls, df: DataFrame) -> None:
        """Validate a DataFrame against the historical OHLCV schema."""
        _validate_columns(df, cls.COLUMNS, "HistoricalOHLCV")
        _validate_no_broker_columns(df, "HistoricalOHLCV")

    @classmethod
    def empty(cls) -> DataFrame:
        """Return an empty DataFrame with the correct schema."""
        return DataFrame(columns=cls.COLUMNS).astype(
            {
                "open": "float64",
                "high": "float64",
                "low": "float64",
                "close": "float64",
                "volume": "int64",
                "oi": "int64",
                "symbol": "string",
                "exchange": "string",
                "timeframe": "string",
            }
        )


class QuoteSchema:
    """Real-time quote schema."""

    COLUMNS: list[str] = [
        "symbol",
        "exchange",
        "ltp",
        "bid",
        "ask",
        "volume",
        "oi",
        "timestamp",
    ]

    COLUMN_TYPES: dict[str, str] = {
        "symbol": "string",
        "exchange": "string",
        "ltp": "float64",
        "bid": "float64",
        "ask": "float64",
        "volume": "int64",
        "oi": "int64",
        "timestamp": "datetime64[ns, UTC]",
    }

    @classmethod
    def validate(cls, df: DataFrame) -> None:
        _validate_columns(df, cls.COLUMNS, "Quote")
        _validate_no_broker_columns(df, "Quote")

    @classmethod
    def empty(cls) -> DataFrame:
        return DataFrame(columns=cls.COLUMNS).astype(
            {
                "ltp": "float64",
                "bid": "float64",
                "ask": "float64",
                "volume": "int64",
                "oi": "int64",
                "symbol": "string",
                "exchange": "string",
            }
        )


class OptionChainSchema:
    """Option chain schema with Greeks."""

    COLUMNS: list[str] = [
        "underlying",
        "expiry",
        "strike",
        "option_type",
        "ltp",
        "bid",
        "ask",
        "volume",
        "oi",
        "iv",
        "delta",
        "gamma",
        "theta",
        "vega",
        "rho",
        "timestamp",
    ]

    COLUMN_TYPES: dict[str, str] = {
        "underlying": "string",
        "expiry": "string",
        "strike": "float64",
        "option_type": "string",
        "ltp": "float64",
        "bid": "float64",
        "ask": "float64",
        "volume": "int64",
        "oi": "int64",
        "iv": "float64",
        "delta": "float64",
        "gamma": "float64",
        "theta": "float64",
        "vega": "float64",
        "rho": "float64",
        "timestamp": "datetime64[ns, UTC]",
    }

    @classmethod
    def validate(cls, df: DataFrame) -> None:
        _validate_columns(df, cls.COLUMNS, "OptionChain")
        _validate_no_broker_columns(df, "OptionChain")

    @classmethod
    def empty(cls) -> DataFrame:
        return DataFrame(columns=cls.COLUMNS).astype(
            {
                "strike": "float64",
                "ltp": "float64",
                "bid": "float64",
                "ask": "float64",
                "volume": "int64",
                "oi": "int64",
                "iv": "float64",
                "delta": "float64",
                "gamma": "float64",
                "theta": "float64",
                "vega": "float64",
                "rho": "float64",
                "underlying": "string",
                "expiry": "string",
                "option_type": "string",
            }
        )


_DEPTH_LEVELS = 20


def _build_depth_columns() -> list[str]:
    cols = ["symbol", "timestamp"]
    for i in range(1, _DEPTH_LEVELS + 1):
        cols.extend(
            [
                f"bid_price_{i}",
                f"bid_qty_{i}",
                f"ask_price_{i}",
                f"ask_qty_{i}",
            ]
        )
    return cols


_DEPTH_COLUMNS: list[str] = _build_depth_columns()


class MarketDepthSchema:
    """L2 market depth schema (20 levels)."""

    LEVELS = _DEPTH_LEVELS
    COLUMNS = _DEPTH_COLUMNS

    @classmethod
    def column_names(cls) -> list[str]:
        return list(cls.COLUMNS)

    @classmethod
    def validate(cls, df: DataFrame) -> None:
        _validate_columns(df, cls.COLUMNS, "MarketDepth")
        _validate_no_broker_columns(df, "MarketDepth")

    @classmethod
    def empty(cls) -> DataFrame:
        return DataFrame(columns=cls.column_names())


class PositionsSchema:
    """Canonical positions schema (list of dataclass instances, NOT DataFrame)."""

    pass


class OrdersSchema:
    """Canonical orders schema (list of dataclass instances, NOT DataFrame)."""

    pass


# ── Forbidden broker-specific columns ──────────────────────────────────────

FORBIDDEN_COLUMNS: set[str] = {
    "security_id",
    "instrument_token",
    "exchange_token",
    "symbol_token",
}


# ── Validation helpers ─────────────────────────────────────────────────────


def _validate_columns(df: DataFrame, expected: list[str], schema_name: str) -> None:
    """Validate that a DataFrame has exactly the expected columns."""
    actual = set(df.columns)
    expected_set = set(expected)

    missing = expected_set - actual
    extra = actual - expected_set

    errors: list[str] = []
    if missing:
        errors.append(f"Missing columns: {sorted(missing)}")
    if extra:
        errors.append(f"Unexpected columns: {sorted(extra)}")

    if errors:
        raise ValueError(
            f"{schema_name} schema violation: {'; '.join(errors)}. Expected columns: {expected}"
        )


def _validate_no_broker_columns(df: DataFrame, schema_name: str) -> None:
    """Ensure no broker-specific column names leaked outside adapter."""
    leaked = FORBIDDEN_COLUMNS & set(df.columns)
    if leaked:
        raise ValueError(
            f"{schema_name} contains broker-specific columns that "
            f"must not leak outside adapter boundary: {sorted(leaked)}"
        )


def validate_dataframe(
    df: DataFrame,
    schema: type,
    context: str = "",
) -> None:
    """Validate a DataFrame against a schema class."""
    schema.validate(df)


# ── DataFrame constructors ─────────────────────────────────────────────────


def build_historical_df(
    rows: Sequence[dict[str, Any]],
    symbol: str = "",
    exchange: str = "",
    timeframe: str = "1d",
) -> DataFrame:
    """Build a canonical Historical OHLCV DataFrame from raw rows.

    Each row should contain: timestamp, open, high, low, close, volume, oi.
    Symbol, exchange, and timeframe are filled if missing.
    """
    if not rows:
        return HistoricalSchema.empty()

    df = pd.DataFrame(rows)

    # Ensure required columns exist
    for col in HistoricalSchema.COLUMNS:
        if col not in df.columns:
            if col == "oi":
                df[col] = 0
            elif col in ("symbol", "exchange", "timeframe"):
                df[col] = ""
            elif col == "volume":
                df[col] = 0

    # Fill metadata columns
    if symbol:
        df["symbol"] = symbol
    if exchange:
        df["exchange"] = exchange
    if timeframe:
        df["timeframe"] = timeframe

    # Normalize timestamps
    if "timestamp" in df.columns:
        df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True, errors="coerce")

    # Coerce numeric columns
    for col in ("open", "high", "low", "close"):
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0)
    df["volume"] = pd.to_numeric(df["volume"], errors="coerce").fillna(0).astype("int64")
    df["oi"] = pd.to_numeric(df["oi"], errors="coerce").fillna(0).astype("int64")

    # Ensure string columns
    for col in ("symbol", "exchange", "timeframe"):
        df[col] = df[col].astype("string")

    # Select and order columns
    df = df[HistoricalSchema.COLUMNS]

    return df


def build_quote_df(
    symbol: str,
    exchange: str,
    ltp: float | Decimal | int = 0,
    bid: float | Decimal | int = 0,
    ask: float | Decimal | int = 0,
    volume: int = 0,
    oi: int = 0,
    timestamp: datetime | None = None,
) -> DataFrame:
    """Build a canonical Quote DataFrame with one row."""
    ts = timestamp or datetime.now(timezone.utc)
    if hasattr(ts, "astimezone") and ts.tzinfo is None:
        import datetime as _dt

        ts = ts.replace(tzinfo=_dt.timezone.utc)

    row = {
        "symbol": str(symbol),
        "exchange": str(exchange),
        "ltp": float(ltp),
        "bid": float(bid),
        "ask": float(ask),
        "volume": int(volume),
        "oi": int(oi),
        "timestamp": pd.Timestamp(ts),
    }
    df = pd.DataFrame([row])
    for col in ("symbol", "exchange"):
        df[col] = df[col].astype("string")
    return df[QuoteSchema.COLUMNS]


def build_option_chain_df(
    rows: Sequence[dict[str, Any]],
) -> DataFrame:
    """Build a canonical Option Chain DataFrame."""
    if not rows:
        return OptionChainSchema.empty()

    df = pd.DataFrame(rows)

    # Ensure all columns exist with NaN defaults
    for col in OptionChainSchema.COLUMNS:
        if col not in df.columns:
            if col in ("delta", "gamma", "theta", "vega", "rho", "iv"):
                df[col] = float("nan")
            elif col in ("volume", "oi"):
                df[col] = 0
            elif col in ("ltp", "bid", "ask", "strike"):
                df[col] = 0.0
            else:
                df[col] = ""

    # Normalize
    if "timestamp" in df.columns:
        df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True, errors="coerce")

    for col in ("ltp", "bid", "ask", "strike", "iv", "delta", "gamma", "theta", "vega", "rho"):
        df[col] = pd.to_numeric(df[col], errors="coerce")
    for col in ("volume", "oi"):
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype("int64")
    for col in ("underlying", "expiry", "option_type"):
        df[col] = df[col].astype("string")

    return df[OptionChainSchema.COLUMNS]


def build_market_depth_df(
    symbol: str,
    bids: list[dict[str, Any]],
    asks: list[dict[str, Any]],
    timestamp: datetime | None = None,
) -> DataFrame:
    """Build a canonical Market Depth DataFrame (20 levels)."""
    ts = timestamp or datetime.now(timezone.utc)
    row: dict[str, Any] = {
        "symbol": str(symbol),
        "timestamp": pd.Timestamp(ts),
    }

    for i in range(1, MarketDepthSchema.LEVELS + 1):
        bid = bids[i - 1] if i - 1 < len(bids) else {}
        ask = asks[i - 1] if i - 1 < len(asks) else {}
        row[f"bid_price_{i}"] = float(bid.get("price", 0))
        row[f"bid_qty_{i}"] = int(bid.get("quantity", 0))
        row[f"ask_price_{i}"] = float(ask.get("price", 0))
        row[f"ask_qty_{i}"] = int(ask.get("quantity", 0))

    df = pd.DataFrame([row])
    df["symbol"] = df["symbol"].astype("string")
    return df[MarketDepthSchema.column_names()]
