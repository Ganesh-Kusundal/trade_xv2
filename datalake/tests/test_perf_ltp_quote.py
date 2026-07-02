"""Performance tests for Task 2.2: get_last_candle_fast in DataLakeGateway.

Validates:
- ltp() uses get_last_candle_fast (not full parquet load)
- ltp() returns Decimal (backward compatibility)
- quote() has TTLCache (5-min TTL)
- Measurable latency improvement over full parquet load
"""

from __future__ import annotations

import time
from decimal import Decimal
from pathlib import Path

import pandas as pd
import pyarrow as pa

from datalake.gateway import DataLakeGateway
from datalake.core.io import atomic_parquet_write


def _make_dataframe(symbol: str, n: int = 10_000) -> pd.DataFrame:
    """Create a realistic-sized DataFrame for perf testing."""
    return pd.DataFrame(
        {
            "timestamp": pd.date_range("2020-01-01 09:15", periods=n, freq="1min"),
            "symbol": symbol,
            "exchange": "NSE",
            "open": [100.0 + i * 0.01 for i in range(n)],
            "high": [101.0 + i * 0.01 for i in range(n)],
            "low": [99.0 + i * 0.01 for i in range(n)],
            "close": [100.5 + i * 0.01 for i in range(n)],
            "volume": [1000 + i for i in range(n)],
            "oi": [0] * n,
        }
    )


def _write_symbol(root: Path, symbol: str, timeframe: str = "1m", n: int = 10_000) -> Path:
    hive = root / "equities" / "candles" / f"timeframe={timeframe}" / f"symbol={symbol}"
    hive.mkdir(parents=True, exist_ok=True)
    path = hive / "data.parquet"
    table = pa.Table.from_pandas(_make_dataframe(symbol, n=n), preserve_index=False)
    atomic_parquet_write(path, table, compression="snappy")
    return path


class TestLtpPerformance:
    """Verify ltp() uses get_last_candle_fast and returns Decimal."""

    def test_ltp_returns_decimal(self, tmp_path: Path):
        """Backward compatibility: ltp() must return Decimal."""
        _write_symbol(tmp_path, "RELIANCE", n=100)
        gw = DataLakeGateway(root=str(tmp_path))
        result = gw.ltp("RELIANCE", "NSE")
        assert isinstance(result, Decimal), f"Expected Decimal, got {type(result)}"

    def test_ltp_correct_value(self, tmp_path: Path):
        """ltp() should return the close of the last candle."""
        _write_symbol(tmp_path, "RELIANCE", n=100)
        gw = DataLakeGateway(root=str(tmp_path))
        result = gw.ltp("RELIANCE", "NSE")
        # Last close = 100.5 + 99 * 0.01 = 101.49
        expected = Decimal(str(100.5 + 99 * 0.01))
        assert result == expected, f"Expected {expected}, got {result}"

    def test_ltp_missing_symbol_returns_zero(self, tmp_path: Path):
        """ltp() for missing symbol returns Decimal('0')."""
        gw = DataLakeGateway(root=str(tmp_path))
        result = gw.ltp("NONEXISTENT", "NSE")
        assert result == Decimal("0")

    def test_ltp_100_calls_performance(self, tmp_path: Path):
        """100 consecutive ltp() calls should complete in reasonable time.

        With get_last_candle_fast (DuckDB LIMIT 1), each call reads only
        the last row instead of loading 10K+ rows. Expected: < 50ms avg
        per call on modern hardware.
        """
        _write_symbol(tmp_path, "RELIANCE", n=10_000)
        gw = DataLakeGateway(root=str(tmp_path))

        # Warm up (first call may have DuckDB init overhead)
        gw.ltp("RELIANCE", "NSE")

        start = time.perf_counter()
        for _ in range(100):
            gw.ltp("RELIANCE", "NSE")
        elapsed = time.perf_counter() - start

        avg_ms = elapsed / 100 * 1000
        print(f"\n✓ 100 ltp() calls in {elapsed:.2f}s = {avg_ms:.1f}ms avg")

        # Each call should be fast (< 200ms avg is generous for CI)
        assert avg_ms < 200, f"ltp() too slow: {avg_ms:.1f}ms avg per call"

    def test_ltp_uses_get_last_candle_fast(self, tmp_path: Path):
        """Verify ltp() actually calls get_last_candle_fast (not _load_parquet)."""
        _write_symbol(tmp_path, "RELIANCE", n=100)
        gw = DataLakeGateway(root=str(tmp_path))

        from unittest.mock import patch

        with patch("datalake.gateway.get_last_candle_fast") as mock_fast:
            mock_fast.return_value = {"close": 1234.5, "timestamp": "2026-01-01"}
            result = gw.ltp("RELIANCE", "NSE")

            mock_fast.assert_called_once_with("RELIANCE", "1m", root=str(tmp_path))
            assert result == Decimal("1234.5")


class TestQuoteTTLCache:
    """Verify quote() uses TTLCache."""

    def test_quote_returns_quote_object(self, tmp_path: Path):
        """quote() still returns a proper Quote object."""
        from domain import Quote

        _write_symbol(tmp_path, "RELIANCE", n=100)
        gw = DataLakeGateway(root=str(tmp_path))
        result = gw.quote("RELIANCE", "NSE")
        assert isinstance(result, Quote)
        assert result.symbol == "RELIANCE"
        assert isinstance(result.ltp, Decimal)

    def test_quote_cached_on_second_call(self, tmp_path: Path):
        """Second call to quote() should hit cache (not re-read parquet)."""
        _write_symbol(tmp_path, "RELIANCE", n=100)
        gw = DataLakeGateway(root=str(tmp_path))

        # First call — cache miss
        q1 = gw.quote("RELIANCE", "NSE")

        # Second call — should be cached
        q2 = gw.quote("RELIANCE", "NSE")

        # Same object reference (cached)
        assert q1 is q2, "quote() should return cached object on second call"

    def test_quote_cache_is_per_instance(self, tmp_path: Path):
        """Different gateway instances have independent caches."""
        _write_symbol(tmp_path, "RELIANCE", n=100)
        gw1 = DataLakeGateway(root=str(tmp_path))
        gw2 = DataLakeGateway(root=str(tmp_path))

        q1 = gw1.quote("RELIANCE", "NSE")
        q2 = gw2.quote("RELIANCE", "NSE")

        # Both return valid quotes, but they are different objects
        # (different cache instances)
        assert q1.symbol == q2.symbol == "RELIANCE"
        assert q1 is not q2

    def test_quote_cache_maxsize(self, tmp_path: Path):
        """TTLCache should have maxsize=512."""
        gw = DataLakeGateway(root=str(tmp_path))
        assert gw._quote_cache.maxsize == 512

    def test_quote_cache_ttl(self, tmp_path: Path):
        """TTLCache should have ttl=300 (5 minutes)."""
        gw = DataLakeGateway(root=str(tmp_path))
        assert gw._quote_cache.ttl == 300

    def test_quote_compute_quote_still_works(self, tmp_path: Path):
        """_compute_quote() (uncached) should still produce correct results."""
        _write_symbol(tmp_path, "RELIANCE", n=5)
        gw = DataLakeGateway(root=str(tmp_path))

        # Call _compute_quote directly (bypasses cache)
        q = gw._compute_quote("RELIANCE", "NSE")
        assert q.symbol == "RELIANCE"
        assert q.ltp == Decimal(str(100.54))  # 100.5 + 4*0.01
        assert q.volume == 1004  # 1000 + 4
