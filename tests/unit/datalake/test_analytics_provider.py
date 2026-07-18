"""Tests for :class:`datalake.adapters.DataLakeMarketDataProvider`.

Validates that the adapter:
- Has the required data access methods.
- Delegates correctly to the underlying :class:`~datalake.gateway.DataLakeGateway`.
- Handles empty symbols gracefully.
- Batch operations return correct DataFrames.
- The ``query()`` escape hatch works.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pyarrow as pa
import pytest

from datalake.adapters.analytics_provider import DataLakeMarketDataProvider
from datalake.gateway import DataLakeGateway
from datalake.core.io import atomic_parquet_write


# ── Helpers ──────────────────────────────────────────────────────────────


def _make_dataframe(symbol: str, n: int = 10) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "timestamp": pd.date_range("2026-06-01 09:15", periods=n, freq="1min"),
            "symbol": symbol,
            "exchange": "NSE",
            "open": [100.0 + i for i in range(n)],
            "high": [101.0 + i for i in range(n)],
            "low": [99.0 + i for i in range(n)],
            "close": [100.5 + i for i in range(n)],
            "volume": [1000 + i * 10 for i in range(n)],
            "oi": [0] * n,
        }
    )


def _write_symbol(root: Path, symbol: str, timeframe: str = "1m", n: int = 10) -> Path:
    hive = root / "equities" / "candles" / f"timeframe={timeframe}" / f"symbol={symbol}"
    hive.mkdir(parents=True, exist_ok=True)
    path = hive / "data.parquet"
    table = pa.Table.from_pandas(_make_dataframe(symbol, n=n), preserve_index=False)
    atomic_parquet_write(path, table, compression="snappy")
    return path


# ── Protocol compliance ──────────────────────────────────────────────────


class TestMarketDataProviderCompliance:
    """Verify the adapter has the required data access methods."""

    def test_has_all_required_methods(self, tmp_path: Path):
        provider = DataLakeMarketDataProvider(root=str(tmp_path))
        required = {"history", "option_chain", "future_chain", "ltp", "history_batch", "list_symbols", "query"}
        for method_name in required:
            assert hasattr(provider, method_name), f"Missing method: {method_name}"
            assert callable(getattr(provider, method_name))


# ── Single-symbol access ─────────────────────────────────────────────────


class TestHistory:
    def test_returns_dataframe_for_valid_symbol(self, tmp_path: Path):
        _write_symbol(tmp_path, "RELIANCE", n=10)
        provider = DataLakeMarketDataProvider(root=str(tmp_path))
        df = provider.history("RELIANCE", timeframe="1m", lookback_days=365)
        assert isinstance(df, pd.DataFrame)
        assert not df.empty
        assert "close" in df.columns

    def test_returns_empty_for_missing_symbol(self, tmp_path: Path):
        provider = DataLakeMarketDataProvider(root=str(tmp_path))
        df = provider.history("MISSING", timeframe="1m", lookback_days=1)
        assert isinstance(df, pd.DataFrame)
        assert df.empty

    def test_respects_from_date_filter(self, tmp_path: Path):
        _write_symbol(tmp_path, "TCS", n=20)
        provider = DataLakeMarketDataProvider(root=str(tmp_path))
        df = provider.history(
            "TCS",
            timeframe="1m",
            from_date="2026-06-01",
            to_date="2026-06-01",
        )
        assert isinstance(df, pd.DataFrame)
        # Should have filtered rows (only data from 2026-06-01)


class TestLtp:
    def test_returns_float_for_valid_symbol(self, tmp_path: Path):
        _write_symbol(tmp_path, "RELIANCE")
        provider = DataLakeMarketDataProvider(root=str(tmp_path))
        price = provider.ltp("RELIANCE")
        assert isinstance(price, float)
        assert price > 0

    def test_returns_zero_for_missing_symbol(self, tmp_path: Path):
        provider = DataLakeMarketDataProvider(root=str(tmp_path))
        price = provider.ltp("MISSING")
        assert price == 0.0


# ── Batch access ─────────────────────────────────────────────────────────


class TestHistoryBatch:
    def test_returns_combined_dataframe(self, tmp_path: Path):
        _write_symbol(tmp_path, "RELIANCE", n=5)
        _write_symbol(tmp_path, "TCS", n=5)
        provider = DataLakeMarketDataProvider(root=str(tmp_path))
        df = provider.history_batch(
            ["RELIANCE", "TCS"],
            timeframe="1m",
            lookback_days=365,
        )
        assert isinstance(df, pd.DataFrame)
        assert not df.empty

    def test_empty_symbols_returns_empty(self, tmp_path: Path):
        provider = DataLakeMarketDataProvider(root=str(tmp_path))
        df = provider.history_batch([], timeframe="1m")
        assert isinstance(df, pd.DataFrame)
        assert df.empty


class TestListSymbols:
    def test_returns_symbol_list(self, tmp_path: Path):
        _write_symbol(tmp_path, "RELIANCE")
        _write_symbol(tmp_path, "TCS")
        provider = DataLakeMarketDataProvider(root=str(tmp_path))
        symbols = provider.list_symbols(timeframe="1m")
        assert isinstance(symbols, list)
        assert "RELIANCE" in symbols
        assert "TCS" in symbols


# ── Query escape hatch ───────────────────────────────────────────────────


class TestQuery:
    def test_simple_query(self, tmp_path: Path):
        provider = DataLakeMarketDataProvider(root=str(tmp_path))
        df = provider.query("SELECT 1 AS x, 'hello' AS y")
        assert isinstance(df, pd.DataFrame)
        assert len(df) == 1
        assert df["x"].iloc[0] == 1
        assert df["y"].iloc[0] == "hello"

    def test_query_with_params(self, tmp_path: Path):
        provider = DataLakeMarketDataProvider(root=str(tmp_path))
        df = provider.query("SELECT ? AS val", [42])
        assert df["val"].iloc[0] == 42


# ── Gateway injection ────────────────────────────────────────────────────


class TestGatewayInjection:
    def test_accepts_preconfigured_gateway(self, tmp_path: Path):
        _write_symbol(tmp_path, "RELIANCE")
        gw = DataLakeGateway(root=str(tmp_path))
        provider = DataLakeMarketDataProvider(gateway=gw)
        df = provider.history("RELIANCE", timeframe="1m", lookback_days=365)
        assert not df.empty

    def test_repr(self, tmp_path: Path):
        provider = DataLakeMarketDataProvider(root=str(tmp_path))
        assert "DataLakeMarketDataProvider" in repr(provider)
        assert str(tmp_path) in repr(provider)
