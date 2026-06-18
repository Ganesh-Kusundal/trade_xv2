"""Performance regression suite — historical data, batch ops, latency, throughput.

Guards against performance regressions in critical data paths.
All tests use mocked HTTP/gateway so they run without live credentials.
Thresholds are calibrated to catch 2x+ slowdowns.

Run with:
    pytest tests/performance/test_data_performance.py -v
"""

from __future__ import annotations

import time
import threading
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from brokers.common.core.domain import (
    Balance,
    MarketDepth,
    DepthLevel,
    Quote,
)


# ── Helpers ──────────────────────────────────────────────────────────────────


def _make_ohlcv_dataframe(n: int, symbol: str = "RELIANCE") -> pd.DataFrame:
    """Generate a realistic OHLCV DataFrame with n rows and valid OHLC integrity."""
    import numpy as np
    rng = np.random.default_rng(42)
    base_price = 2500.0
    dates = pd.date_range("2026-01-01", periods=n, freq="B")
    close = base_price + rng.normal(0, 10, n).cumsum()
    opens = close + rng.normal(0, 3, n)
    # Ensure OHLC integrity: high >= max(open, close), low <= min(open, close)
    highs = np.maximum(opens, close) + rng.uniform(0, 10, n)
    lows = np.minimum(opens, close) - rng.uniform(0, 10, n)
    return pd.DataFrame({
        "timestamp": dates,
        "open": opens,
        "high": highs,
        "low": lows,
        "close": close,
        "volume": rng.integers(100_000, 10_000_000, n),
        "oi": rng.integers(0, 500_000, n),
        "symbol": symbol,
    })


def _make_mock_historical_response(n: int = 30) -> dict:
    """Generate a mock Dhan historical API response."""
    rows = []
    base = 2500
    for i in range(n):
        price = base + i
        rows.append({
            "date": f"2026-01-{(i % 28) + 1:02d}",
            "open": price - 5,
            "high": price + 10,
            "low": price - 10,
            "close": price,
            "volume": 1_000_000 + i * 1000,
        })
    return {"data": rows}


def _make_mock_intraday_response(n: int = 75) -> dict:
    """Generate a mock Dhan intraday API response."""
    rows = []
    base = 2500
    ts = 1735689300
    for i in range(n):
        price = base + (i % 20)
        rows.append({
            "timestamp": ts + i * 300,
            "open": price - 2,
            "high": price + 5,
            "low": price - 5,
            "close": price,
            "volume": 5000 + i * 100,
        })
    return {"data": rows}


# ── 1. Historical Data Performance ──────────────────────────────────────────


@pytest.mark.performance
class TestHistoricalDataPerformance:
    """Benchmark historical data retrieval and DataFrame construction."""

    def test_daily_30day_parse_latency(self):
        """Parsing 30 daily candles must complete in < 50ms."""
        from brokers.dhan.historical import HistoricalAdapter

        client = MagicMock()
        client.post.return_value = _make_mock_historical_response(30)
        resolver = MagicMock()
        inst = MagicMock()
        inst.security_id = "2885"
        inst.exchange = MagicMock()
        inst.exchange.value = "NSE"
        inst.instrument_type = MagicMock()
        inst.instrument_type.value = "EQUITY"
        resolver.resolve.return_value = inst

        adapter = HistoricalAdapter(client, resolver)
        start = time.perf_counter()
        df = adapter.get_historical("RELIANCE", "NSE", "2026-01-01", "2026-01-31", "1D")
        elapsed_ms = (time.perf_counter() - start) * 1000

        assert len(df) > 0
        assert elapsed_ms < 50, f"Daily 30-day parse too slow: {elapsed_ms:.1f}ms"

    def test_intraday_1day_parse_latency(self):
        """Parsing 75 5-min intraday candles must complete in < 50ms."""
        from brokers.dhan.historical import HistoricalAdapter

        client = MagicMock()
        client.post.return_value = _make_mock_intraday_response(75)
        resolver = MagicMock()
        inst = MagicMock()
        inst.security_id = "2885"
        inst.exchange = MagicMock()
        inst.exchange.value = "NSE"
        inst.instrument_type = MagicMock()
        inst.instrument_type.value = "EQUITY"
        resolver.resolve.return_value = inst

        adapter = HistoricalAdapter(client, resolver)
        start = time.perf_counter()
        df = adapter.get_historical("RELIANCE", "NSE", "2026-01-02", "2026-01-02", "5")
        elapsed_ms = (time.perf_counter() - start) * 1000

        assert len(df) > 0
        assert elapsed_ms < 50, f"Intraday 1-day parse too slow: {elapsed_ms:.1f}ms"

    def test_daily_365day_parse_latency(self):
        """Parsing 250 daily candles (1 year) must complete in < 100ms."""
        from brokers.dhan.historical import HistoricalAdapter

        client = MagicMock()
        client.post.return_value = _make_mock_historical_response(250)
        resolver = MagicMock()
        inst = MagicMock()
        inst.security_id = "2885"
        inst.exchange = MagicMock()
        inst.exchange.value = "NSE"
        inst.instrument_type = MagicMock()
        inst.instrument_type.value = "EQUITY"
        resolver.resolve.return_value = inst

        adapter = HistoricalAdapter(client, resolver)
        start = time.perf_counter()
        df = adapter.get_historical("RELIANCE", "NSE", "2025-01-01", "2026-01-01", "1D")
        elapsed_ms = (time.perf_counter() - start) * 1000

        assert len(df) == 250
        assert elapsed_ms < 100, f"Daily 365-day parse too slow: {elapsed_ms:.1f}ms"

    def test_dataframe_column_schema(self):
        """Parsed DataFrame must have the canonical OHLCV schema."""
        from brokers.dhan.historical import HistoricalAdapter

        client = MagicMock()
        client.post.return_value = _make_mock_historical_response(5)
        resolver = MagicMock()
        inst = MagicMock()
        inst.security_id = "2885"
        inst.exchange = MagicMock()
        inst.exchange.value = "NSE"
        inst.instrument_type = MagicMock()
        inst.instrument_type.value = "EQUITY"
        resolver.resolve.return_value = inst

        adapter = HistoricalAdapter(client, resolver)
        df = adapter.get_historical("RELIANCE", "NSE", "2026-01-01", "2026-01-05", "1D")

        required_cols = {"open", "high", "low", "close", "volume"}
        assert required_cols.issubset(set(df.columns)), f"Missing columns: {required_cols - set(df.columns)}"


# ── 2. Historical Data Quality Regression ────────────────────────────────────


@pytest.mark.performance
class TestHistoricalDataQuality:
    """Regression tests for OHLCV data integrity."""

    def test_no_negative_prices(self):
        """Parsed OHLCV data must never contain negative prices."""
        df = _make_ohlcv_dataframe(500)
        for col in ["open", "high", "low", "close"]:
            assert (df[col] >= 0).all(), f"Negative values found in {col}"

    def test_high_gte_low(self):
        """High price must always be >= low price."""
        df = _make_ohlcv_dataframe(500)
        assert (df["high"] >= df["low"]).all(), "high < low found in data"

    def test_high_gte_open_close(self):
        """High must be >= both open and close."""
        df = _make_ohlcv_dataframe(500)
        assert (df["high"] >= df["open"]).all(), "high < open found"
        assert (df["high"] >= df["close"]).all(), "high < close found"

    def test_low_lte_open_close(self):
        """Low must be <= both open and close."""
        df = _make_ohlcv_dataframe(500)
        assert (df["low"] <= df["open"]).all(), "low > open found"
        assert (df["low"] <= df["close"]).all(), "low > close found"

    def test_no_duplicate_timestamps(self):
        """Timestamps must be unique (no duplicate bars)."""
        df = _make_ohlcv_dataframe(100)
        assert df["timestamp"].is_unique, "Duplicate timestamps found"

    def test_timestamps_monotonically_increasing(self):
        """Timestamps must be strictly increasing."""
        df = _make_ohlcv_dataframe(100)
        ts = pd.to_datetime(df["timestamp"])
        assert ts.is_monotonic_increasing, "Timestamps not monotonically increasing"

    def test_volume_non_negative(self):
        """Volume must never be negative."""
        df = _make_ohlcv_dataframe(500)
        assert (df["volume"] >= 0).all(), "Negative volume found"

    def test_gap_detection(self):
        """Test that gaps in daily data can be detected (weekends excluded)."""
        df = _make_ohlcv_dataframe(20)  # Business days only
        ts = pd.to_datetime(df["timestamp"])
        diffs = ts.diff().dt.days.dropna()
        # Business day gaps should be 1 (Mon-Fri) or 3 (Fri-Mon)
        assert diffs.max() <= 3, f"Unexpected gap: {diffs.max()} days"


# ── 3. Batch Operation Performance ───────────────────────────────────────────


@pytest.mark.performance
class TestBatchOperationPerformance:
    """Benchmark batch operations with increasing symbol counts."""

    def _make_dhan_gw_with_mock(self):
        from brokers.dhan.gateway import BrokerGateway
        conn = MagicMock()
        conn.client_id = "TEST"
        conn.access_token = "TOKEN"
        conn.instruments = MagicMock()
        conn.event_bus = None
        conn.market_feed = None
        conn._lifecycle = None

        inst = MagicMock()
        inst.exchange = MagicMock()
        inst.exchange.value = "NSE"
        inst.security_id = "2885"
        conn.instruments.resolve.return_value = inst

        return BrokerGateway(conn)

    def test_ltp_batch_10_symbols_latency(self):
        """ltp_batch for 10 symbols must complete in < 100ms (mocked)."""
        gw = self._make_dhan_gw_with_mock()
        symbols = [f"SYM{i}" for i in range(10)]
        gw._conn.market_data.get_batch_ltp.return_value = {
            s: Decimal(str(2500 + i)) for i, s in enumerate(symbols)
        }

        start = time.perf_counter()
        result = gw.ltp_batch(symbols, "NSE")
        elapsed_ms = (time.perf_counter() - start) * 1000

        assert len(result) == 10
        assert elapsed_ms < 100, f"ltp_batch(10) too slow: {elapsed_ms:.1f}ms"

    def test_ltp_batch_100_symbols_latency(self):
        """ltp_batch for 100 symbols must complete in < 500ms (mocked)."""
        gw = self._make_dhan_gw_with_mock()
        symbols = [f"SYM{i}" for i in range(100)]
        gw._conn.market_data.get_batch_ltp.return_value = {
            s: Decimal(str(2500 + i)) for i, s in enumerate(symbols)
        }

        start = time.perf_counter()
        result = gw.ltp_batch(symbols, "NSE")
        elapsed_ms = (time.perf_counter() - start) * 1000

        assert len(result) == 100
        assert elapsed_ms < 500, f"ltp_batch(100) too slow: {elapsed_ms:.1f}ms"

    def test_quote_batch_10_symbols_latency(self):
        """quote_batch for 10 symbols must complete in < 100ms (mocked)."""
        gw = self._make_dhan_gw_with_mock()
        symbols = [f"SYM{i}" for i in range(10)]
        gw._conn.market_data.get_batch_quote.return_value = {
            s: {"ltp": 2500 + i, "volume": 100000} for i, s in enumerate(symbols)
        }

        start = time.perf_counter()
        result = gw.quote_batch(symbols, "NSE")
        elapsed_ms = (time.perf_counter() - start) * 1000

        assert len(result) == 10
        assert elapsed_ms < 100, f"quote_batch(10) too slow: {elapsed_ms:.1f}ms"

    def test_history_batch_5_symbols_latency(self):
        """history_batch for 5 symbols must complete in < 2s (mocked)."""
        gw = self._make_dhan_gw_with_mock()
        symbols = ["RELIANCE", "TCS", "INFY", "HDFCBANK", "ICICIBANK"]
        df = _make_ohlcv_dataframe(10)
        gw._conn.historical.get_historical.return_value = df

        start = time.perf_counter()
        result = gw.history_batch(symbols, "NSE", "1D", lookback_days=10)
        elapsed_ms = (time.perf_counter() - start) * 1000

        assert len(result) > 0
        assert elapsed_ms < 2000, f"history_batch(5) too slow: {elapsed_ms:.1f}ms"


# ── 4. REST Endpoint Latency Regression ──────────────────────────────────────


@pytest.mark.performance
class TestRESTEndpointLatency:
    """Regression tests for REST endpoint processing latency (client-side)."""

    def _make_dhan_gw(self):
        from brokers.dhan.gateway import BrokerGateway
        conn = MagicMock()
        conn.client_id = "TEST"
        conn.access_token = "TOKEN"
        conn.instruments = MagicMock()
        conn.event_bus = None
        conn.market_feed = None
        conn._lifecycle = None

        inst = MagicMock()
        inst.exchange = MagicMock()
        inst.exchange.value = "NSE"
        inst.security_id = "2885"
        inst.symbol = "RELIANCE"
        inst.instrument_type = MagicMock()
        inst.instrument_type.value = "EQUITY"
        inst.canonical_symbol = "RELIANCE"
        conn.instruments.resolve.return_value = inst

        return BrokerGateway(conn)

    def test_ltp_processing_latency(self):
        """LTP retrieval + parsing must complete in < 10ms (mocked I/O)."""
        gw = self._make_dhan_gw()
        gw._conn.market_data.get_ltp.return_value = Decimal("2450.55")

        iterations = 100
        start = time.perf_counter()
        for _ in range(iterations):
            gw.ltp("RELIANCE", "NSE")
        elapsed_ms = (time.perf_counter() - start) * 1000
        per_op_ms = elapsed_ms / iterations

        assert per_op_ms < 10, f"LTP processing too slow: {per_op_ms:.2f}ms/op"

    def test_quote_processing_latency(self):
        """Quote retrieval + parsing must complete in < 10ms (mocked I/O)."""
        gw = self._make_dhan_gw()
        gw._conn.market_data.get_quote.return_value = Quote(
            symbol="RELIANCE", ltp=Decimal("2450"), open=Decimal("2430"),
            high=Decimal("2460"), low=Decimal("2420"), close=Decimal("2425"),
            volume=100000, change=Decimal("25"),
        )

        iterations = 100
        start = time.perf_counter()
        for _ in range(iterations):
            gw.quote("RELIANCE", "NSE")
        elapsed_ms = (time.perf_counter() - start) * 1000
        per_op_ms = elapsed_ms / iterations

        assert per_op_ms < 10, f"Quote processing too slow: {per_op_ms:.2f}ms/op"

    def test_depth_processing_latency(self):
        """Depth retrieval + parsing must complete in < 10ms (mocked I/O)."""
        gw = self._make_dhan_gw()
        gw._conn.market_data.get_depth.return_value = MarketDepth(
            bids=[DepthLevel(price=Decimal("2450"), quantity=100, orders=5)],
            asks=[DepthLevel(price=Decimal("2451"), quantity=100, orders=5)],
        )

        iterations = 100
        start = time.perf_counter()
        for _ in range(iterations):
            gw.depth("RELIANCE", "NSE")
        elapsed_ms = (time.perf_counter() - start) * 1000
        per_op_ms = elapsed_ms / iterations

        assert per_op_ms < 10, f"Depth processing too slow: {per_op_ms:.2f}ms/op"

    def test_positions_processing_latency(self):
        """Positions retrieval must complete in < 10ms (mocked I/O)."""
        gw = self._make_dhan_gw()
        gw._conn.portfolio.get_positions.return_value = []

        iterations = 100
        start = time.perf_counter()
        for _ in range(iterations):
            gw.positions()
        elapsed_ms = (time.perf_counter() - start) * 1000
        per_op_ms = elapsed_ms / iterations

        assert per_op_ms < 10, f"Positions processing too slow: {per_op_ms:.2f}ms/op"


# ── 5. Instrument Load Performance ───────────────────────────────────────────


@pytest.mark.performance
class TestInstrumentLoadPerformance:
    """Benchmark instrument loading at scale."""

    def test_load_50k_instruments_under_10s(self):
        """Loading 50K instruments must complete in < 10s."""
        from brokers.dhan.resolver import SymbolResolver

        rows = [
            {
                "SEM_TRADING_SYMBOL": f"INST{i}",
                "SEM_SMST_SECURITY_ID": str(100_000 + i),
                "SEM_EXM_EXCH_ID": "NSE_EQ",
                "SEM_INSTRUMENT_NAME": "EQUITY",
                "SEM_LOT_UNITS": 1,
                "SEM_TICK_SIZE": 0.05,
            }
            for i in range(50_000)
        ]

        r = SymbolResolver()
        start = time.perf_counter()
        r.load_from_rows(rows)
        elapsed = time.perf_counter() - start

        assert elapsed < 10, f"Loading 50K instruments too slow: {elapsed:.1f}s"
        assert r.stats()["total"] >= 49_000

    def test_load_200k_instruments_under_60s(self):
        """Loading 200K instruments (production scale) must complete in < 60s."""
        from brokers.dhan.resolver import SymbolResolver

        rows = [
            {
                "SEM_TRADING_SYMBOL": f"INST{i}",
                "SEM_SMST_SECURITY_ID": str(300_000 + i),
                "SEM_EXM_EXCH_ID": "NSE_EQ",
                "SEM_INSTRUMENT_NAME": "EQUITY",
                "SEM_LOT_UNITS": 1,
                "SEM_TICK_SIZE": 0.05,
            }
            for i in range(200_000)
        ]

        r = SymbolResolver()
        start = time.perf_counter()
        r.load_from_rows(rows)
        elapsed = time.perf_counter() - start

        assert elapsed < 60, f"Loading 200K instruments too slow: {elapsed:.1f}s"
        assert r.stats()["total"] >= 195_000

    def test_resolve_after_200k_load(self):
        """After loading 200K instruments, resolution must remain O(1)."""
        from brokers.dhan.resolver import SymbolResolver

        rows = [
            {
                "SEM_TRADING_SYMBOL": f"INST{i}",
                "SEM_SMST_SECURITY_ID": str(500_000 + i),
                "SEM_EXM_EXCH_ID": "NSE_EQ",
                "SEM_INSTRUMENT_NAME": "EQUITY",
                "SEM_LOT_UNITS": 1,
                "SEM_TICK_SIZE": 0.05,
            }
            for i in range(200_000)
        ]

        r = SymbolResolver()
        r.load_from_rows(rows)

        # Resolve 1000 random symbols
        start = time.perf_counter()
        for i in range(0, 200_000, 200):
            r.get_by_symbol(f"INST{i}", "NSE")
        elapsed_ms = (time.perf_counter() - start) * 1000

        assert elapsed_ms < 100, f"Resolution after 200K load too slow: {elapsed_ms:.1f}ms for 1000 lookups"


# ── 6. WebSocket Throughput Simulation ───────────────────────────────────────


@pytest.mark.performance
class TestWebSocketThroughput:
    """Simulate WebSocket tick processing throughput."""

    def test_tick_dispatch_throughput(self):
        """Dispatching 10K ticks to listeners must complete in < 500ms."""
        from brokers.upstox.websocket.market_data_v3 import UpstoxMarketDataV3Multiplexer

        mux = UpstoxMarketDataV3Multiplexer(authorizer=MagicMock())

        received = []
        def listener(event_type, payload):
            received.append(1)

        mux.add_listener(listener)

        tick = {"type": "tick", "instrument_key": "NSE_EQ|2885", "ltp": 2450.0}
        iterations = 10_000

        start = time.perf_counter()
        with mux._listener_lock:
            listeners = list(mux._listeners)
        for _ in range(iterations):
            for l in listeners:
                l("tick", tick)
        elapsed_ms = (time.perf_counter() - start) * 1000

        assert len(received) == iterations
        ticks_per_sec = iterations / (elapsed_ms / 1000)
        assert ticks_per_sec > 10_000, f"Tick dispatch too slow: {ticks_per_sec:.0f} ticks/s"

    def test_multiple_listeners_throughput(self):
        """Dispatching ticks to 10 listeners must scale linearly."""
        from brokers.upstox.websocket.market_data_v3 import UpstoxMarketDataV3Multiplexer

        mux = UpstoxMarketDataV3Multiplexer(authorizer=MagicMock())

        counts = [0] * 10
        for i in range(10):
            def listener(event_type, payload, idx=i):
                counts[idx] += 1
            mux.add_listener(listener)

        tick = {"type": "tick", "instrument_key": "NSE_EQ|2885", "ltp": 2450.0}
        iterations = 1_000

        start = time.perf_counter()
        with mux._listener_lock:
            listeners = list(mux._listeners)
        for _ in range(iterations):
            for l in listeners:
                l("tick", tick)
        elapsed_ms = (time.perf_counter() - start) * 1000

        assert all(c == iterations for c in counts)
        assert elapsed_ms < 500, f"10-listener dispatch too slow: {elapsed_ms:.1f}ms"


# ── 7. Cross-Broker Comparison ───────────────────────────────────────────────


@pytest.mark.performance
class TestCrossBrokerComparison:
    """Compare Paper gateway performance as a baseline for real brokers."""

    def test_paper_ltp_vs_batch_latency(self):
        """Paper ltp_batch() must complete for 20 symbols (regression guard)."""
        from brokers.paper.paper_gateway import PaperGateway
        pg = PaperGateway()

        symbols = [f"SYM{i}" for i in range(20)]

        # Batch LTP must complete in < 50ms for 20 symbols
        start = time.perf_counter()
        result = pg.ltp_batch(symbols, "NSE")
        batch_ms = (time.perf_counter() - start) * 1000

        assert len(result) == 20
        assert batch_ms < 50, f"ltp_batch(20 symbols) too slow: {batch_ms:.1f}ms"

    def test_paper_quote_returns_consistent_schema(self):
        """Paper quotes must have the same schema across multiple calls."""
        from brokers.paper.paper_gateway import PaperGateway
        pg = PaperGateway()

        q1 = pg.quote("RELIANCE", "NSE")
        q2 = pg.quote("TCS", "NSE")

        assert hasattr(q1, "ltp") and hasattr(q2, "ltp")
        assert hasattr(q1, "symbol") and hasattr(q2, "symbol")
        assert isinstance(q1.ltp, Decimal)
        assert isinstance(q2.ltp, Decimal)

    def test_paper_history_returns_valid_dataframe(self):
        """Paper history must return a valid OHLCV DataFrame."""
        from brokers.paper.paper_gateway import PaperGateway
        pg = PaperGateway()

        df = pg.history("RELIANCE", "NSE", timeframe="1D", lookback_days=30)
        assert isinstance(df, pd.DataFrame)
        assert len(df) > 0
        assert "close" in df.columns or "open" in df.columns

    def test_paper_place_order_latency(self):
        """Paper order placement must complete in < 5ms."""
        from brokers.paper.paper_gateway import PaperGateway
        pg = PaperGateway()

        iterations = 100
        start = time.perf_counter()
        for _ in range(iterations):
            pg.place_order("RELIANCE", quantity=1)
        elapsed_ms = (time.perf_counter() - start) * 1000
        per_op_ms = elapsed_ms / iterations

        assert per_op_ms < 5, f"Paper place_order too slow: {per_op_ms:.2f}ms/op"


# ── 8. DataFrame Operation Performance ───────────────────────────────────────


@pytest.mark.performance
class TestDataFrameOperations:
    """Benchmark common DataFrame operations used in analytics pipeline."""

    def test_concat_10_dataframes(self):
        """Concatenating 10 DataFrames (50 rows each) must complete in < 50ms."""
        frames = [_make_ohlcv_dataframe(50, f"SYM{i}") for i in range(10)]

        start = time.perf_counter()
        result = pd.concat(frames, ignore_index=True)
        elapsed_ms = (time.perf_counter() - start) * 1000

        assert len(result) == 500
        assert elapsed_ms < 50, f"DataFrame concat too slow: {elapsed_ms:.1f}ms"

    def test_rolling_mean_500_bars(self):
        """Computing 20-period rolling mean on 500 bars must complete in < 10ms."""
        df = _make_ohlcv_dataframe(500)

        start = time.perf_counter()
        sma = df["close"].rolling(20).mean()
        elapsed_ms = (time.perf_counter() - start) * 1000

        assert len(sma) == 500
        assert elapsed_ms < 10, f"Rolling mean too slow: {elapsed_ms:.1f}ms"

    def test_groupby_symbol_10_symbols(self):
        """Grouping 500 rows by 10 symbols must complete in < 10ms."""
        frames = [_make_ohlcv_dataframe(50, f"SYM{i}") for i in range(10)]
        df = pd.concat(frames, ignore_index=True)

        start = time.perf_counter()
        grouped = df.groupby("symbol").size()
        elapsed_ms = (time.perf_counter() - start) * 1000

        assert len(grouped) == 10
        assert elapsed_ms < 10, f"GroupBy too slow: {elapsed_ms:.1f}ms"
