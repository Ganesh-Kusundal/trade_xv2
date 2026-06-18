"""Tests for :class:`datalake.gateway.DataLakeGateway` (REF-32).

Specifically validates the parallel-batch implementation. We use a
fake ``quote`` method that sleeps for a measurable amount of time
so we can confirm ``quote_batch`` runs the calls concurrently.
"""
from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import pyarrow as pa

from datalake.gateway import DataLakeGateway
from datalake.io import atomic_parquet_write


def _make_dataframe(symbol: str, n: int = 5) -> pd.DataFrame:
    return pd.DataFrame({
        "timestamp": pd.date_range("2026-06-01 09:15", periods=n, freq="1min"),
        "symbol": symbol,
        "exchange": "NSE",
        "open": [100.0] * n,
        "high": [101.0] * n,
        "low": [99.0] * n,
        "close": [100.5] * n,
        "volume": [1000] * n,
        "oi": [0] * n,
    })


def _write_symbol(root: Path, symbol: str, timeframe: str = "1m", n: int = 5) -> Path:
    hive = root / "equities" / "candles" / f"timeframe={timeframe}" / f"symbol={symbol}"
    hive.mkdir(parents=True, exist_ok=True)
    path = hive / "data.parquet"
    table = pa.Table.from_pandas(_make_dataframe(symbol, n=n), preserve_index=False)
    atomic_parquet_write(path, table, compression="snappy")
    return path


def test_quote_batch_returns_quote_per_symbol(tmp_path: Path):
    _write_symbol(tmp_path, "RELIANCE")
    _write_symbol(tmp_path, "TCS")
    gw = DataLakeGateway(root=str(tmp_path))
    results = gw.quote_batch(["RELIANCE", "TCS"], exchange="NSE")
    assert set(results.keys()) == {"RELIANCE", "TCS"}
    assert results["RELIANCE"].symbol == "RELIANCE"
    assert results["TCS"].symbol == "TCS"


def test_ltp_batch_returns_decimal_per_symbol(tmp_path: Path):
    _write_symbol(tmp_path, "RELIANCE")
    _write_symbol(tmp_path, "TCS")
    gw = DataLakeGateway(root=str(tmp_path))
    results = gw.ltp_batch(["RELIANCE", "TCS"], exchange="NSE")
    assert set(results.keys()) == {"RELIANCE", "TCS"}
    # Each row's close is 100.5
    assert results["RELIANCE"] == results["TCS"]


def test_history_batch_concatenates_per_symbol(tmp_path: Path):
    _write_symbol(tmp_path, "RELIANCE", n=10)
    _write_symbol(tmp_path, "TCS", n=10)
    gw = DataLakeGateway(root=str(tmp_path))
    results = gw.history_batch(
        ["RELIANCE", "TCS"],
        exchange="NSE",
        timeframe="1m",
        lookback_days=30,
    )
    # history_batch returns a DataFrame per ABC contract
    assert isinstance(results, pd.DataFrame)
    assert set(results["symbol"].unique()) == {"RELIANCE", "TCS"}
    assert len(results[results["symbol"] == "RELIANCE"]) == 10
    assert len(results[results["symbol"] == "TCS"]) == 10


def test_quote_batch_skips_missing_symbols(tmp_path: Path):
    # Only RELIANCE has data; TCS does not. The batch should still
    # return the RELIANCE result; the TCS slot is omitted because
    # the underlying ``quote()`` returns an empty Quote (not an
    # exception). To test the failure-isolation path, mock the
    # single-item method to raise for one symbol.
    _write_symbol(tmp_path, "RELIANCE")
    gw = DataLakeGateway(root=str(tmp_path))

    original_quote = gw.quote

    def selective_quote(symbol, exchange="NSE"):
        if symbol == "TCS":
            raise FileNotFoundError(f"no data for {symbol}")
        return original_quote(symbol, exchange)

    with patch.object(gw, "quote", side_effect=selective_quote):
        results = gw.quote_batch(["RELIANCE", "TCS"], exchange="NSE")

    assert "RELIANCE" in results
    assert "TCS" not in results


def test_quote_batch_runs_in_parallel(tmp_path: Path):
    """Verify the parallel execution actually happens.

    We instrument ``quote`` to sleep 100ms per call and run a batch
    of 4 symbols. Serial execution would take ~400ms; parallel
    execution with 5 workers takes ~100ms. We allow generous slack
    so the test is not flaky on CI.
    """
    _write_symbol(tmp_path, "RELIANCE")
    _write_symbol(tmp_path, "TCS")
    _write_symbol(tmp_path, "HDFCBANK")
    _write_symbol(tmp_path, "INFY")

    gw = DataLakeGateway(root=str(tmp_path))
    sleep_seconds = 0.1

    def slow_quote(symbol, exchange="NSE"):
        time.sleep(sleep_seconds)
        from decimal import Decimal
        # Return a minimal Quote
        from brokers.common.core.domain import Quote
        return Quote(symbol=symbol, ltp=Decimal("100.0"))

    with patch.object(gw, "quote", side_effect=slow_quote):
        start = time.time()
        results = gw.quote_batch(["RELIANCE", "TCS", "HDFCBANK", "INFY"], exchange="NSE")
        elapsed = time.time() - start

    assert len(results) == 4
    # Serial would be 4 * 0.1 = 0.4s. Parallel should be well under
    # 0.4s. We allow up to 0.35s (overhead + scheduler jitter).
    assert elapsed < 0.35, f"batch took {elapsed:.3f}s, expected < 0.35s"


def test_history_batch_skips_symbols_with_empty_dataframe(tmp_path: Path):
    _write_symbol(tmp_path, "RELIANCE", n=5)
    # TCS has no file → history() returns empty DataFrame.
    gw = DataLakeGateway(root=str(tmp_path))
    results = gw.history_batch(
        ["RELIANCE", "TCS"],
        exchange="NSE",
        timeframe="1m",
        lookback_days=30,
    )
    # history_batch returns a DataFrame per ABC contract
    assert isinstance(results, pd.DataFrame)
    assert "RELIANCE" in results["symbol"].values
    assert "TCS" not in results["symbol"].values  # empty df omitted


def test_batch_execute_is_reusable():
    """The helper itself should be callable with arbitrary fn.

    This is a structural test — it verifies the helper is the
    canonical parallel-fetch primitive so future callers should
    not re-implement their own ``for sym in symbols`` loops.
    """
    gw = DataLakeGateway(root="/tmp")
    # Use a fast side-effect-free function.
    results = gw._batch_execute(lambda x: x * 2, [1, 2, 3, 4])
    assert results == {1: 2, 2: 4, 3: 6, 4: 8}


def test_batch_execute_handles_exceptions():
    gw = DataLakeGateway(root="/tmp")

    def may_fail(x: int) -> int:
        if x == 2:
            raise ValueError("boom")
        return x * 2

    results = gw._batch_execute(may_fail, [1, 2, 3])
    assert results == {1: 2, 3: 6}
    assert 2 not in results


def test_thread_pool_executor_is_used_for_parallelism():
    """Smoke test: ``_batch_execute`` should use ThreadPoolExecutor.

    We patch the executor class to count calls. The point is to
    catch a regression where someone replaces the executor with a
    serial ``for`` loop — the audit called this out as a real risk
    because both implementations are short enough to look
    equivalent at a glance.
    """
    gw = DataLakeGateway(root="/tmp")
    original_init = ThreadPoolExecutor.__init__

    call_count = {"n": 0}

    def counting_init(self, *args, **kwargs):
        call_count["n"] += 1
        return original_init(self, *args, **kwargs)

    with patch.object(ThreadPoolExecutor, "__init__", counting_init):
        gw._batch_execute(lambda x: x, [1, 2, 3])

    assert call_count["n"] == 1, (
        f"expected exactly one ThreadPoolExecutor for the batch, got {call_count['n']}"
    )
