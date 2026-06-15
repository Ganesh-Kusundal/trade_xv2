"""Tests for HistoricalDownloadEngine."""

from __future__ import annotations

from datetime import date, timedelta
from unittest.mock import MagicMock

import pandas as pd
import pytest

from brokers.common.services.download_engine import (
    DownloadConfig,
    DownloadProgress,
    HistoricalDownloadEngine,
)


def _make_gateway():
    """Create a mock gateway with history() returning synthetic data."""
    gw = MagicMock()
    gw.capabilities.return_value = {
        "max_intraday_days": 30,
        "max_daily_days": 3650,
    }

    def _history(symbol, exchange="NSE", timeframe="1D", lookback_days=90, from_date=None, to_date=None):
        from datetime import datetime
        n = 30
        dates = [datetime(2026, 1, 1) + timedelta(days=i) for i in range(n)]
        close = 100 + pd.Series(range(n)).values
        return pd.DataFrame({
            "timestamp": dates,
            "open": close - 1,
            "high": close + 2,
            "low": close - 2,
            "close": close,
            "volume": [100000] * n,
            "oi": [0] * n,
            "symbol": symbol,
            "exchange": exchange,
            "timeframe": timeframe,
        })

    gw.history.side_effect = _history
    return gw


class TestDownloadConfig:
    def test_defaults(self):
        c = DownloadConfig()
        assert c.chunk_days == 365
        assert c.max_retries == 3
        assert c.max_workers == 5
        assert c.dedup is True
        assert c.sort is True

    def test_custom(self):
        c = DownloadConfig(chunk_days=90, max_retries=5, max_workers=10)
        assert c.chunk_days == 90
        assert c.max_retries == 5
        assert c.max_workers == 10


class TestDownloadProgress:
    def test_initial(self):
        p = DownloadProgress(total_symbols=5, start_time=100.0)
        assert p.total_symbols == 5
        assert p.completed_symbols == 0
        assert p.symbol_progress == 0.0

    def test_progress(self):
        p = DownloadProgress(total_symbols=5, total_chunks=10)
        p.completed_symbols = 3
        p.completed_chunks = 6
        assert p.symbol_progress == 0.6
        assert p.chunk_progress == 0.6


class TestHistoricalDownloadEngine:
    def test_single_symbol(self):
        gw = _make_gateway()
        engine = HistoricalDownloadEngine(gw)
        df = engine.download("RELIANCE", years=1)
        assert not df.empty
        assert "symbol" in df.columns
        assert df["symbol"].iloc[0] == "RELIANCE"

    def test_multi_symbol(self):
        gw = _make_gateway()
        engine = HistoricalDownloadEngine(gw)
        df = engine.download(["RELIANCE", "TCS", "INFY"], years=1)
        assert not df.empty
        assert df["symbol"].nunique() == 3

    def test_empty_gateway(self):
        gw = MagicMock()
        gw.capabilities.return_value = {"max_daily_days": 3650}
        gw.history.return_value = pd.DataFrame()
        engine = HistoricalDownloadEngine(gw)
        df = engine.download("RELIANCE", years=1)
        assert df.empty

    def test_dedup(self):
        gw = _make_gateway()
        config = DownloadConfig(dedup=True)
        engine = HistoricalDownloadEngine(gw, config)
        df = engine.download("RELIANCE", years=1)
        # No duplicates expected from single call
        assert df.duplicated(subset=["symbol", "timestamp"]).sum() == 0

    def test_sort(self):
        gw = _make_gateway()
        config = DownloadConfig(sort=True)
        engine = HistoricalDownloadEngine(gw, config)
        df = engine.download("RELIANCE", years=1)
        timestamps = df["timestamp"].tolist()
        assert timestamps == sorted(timestamps)

    def test_chunk_computation(self):
        gw = _make_gateway()
        config = DownloadConfig(chunk_days=90)
        engine = HistoricalDownloadEngine(gw, config)
        chunks = engine._compute_chunks(date(2026, 1, 1), date(2026, 12, 31), 90)
        assert len(chunks) > 1
        # Each chunk should be <= 90 days
        for start, end in chunks:
            assert (end - start).days <= 89

    def test_progress_callback(self):
        gw = _make_gateway()
        progress_calls = []
        engine = HistoricalDownloadEngine(gw, on_progress=lambda p: progress_calls.append(p))
        engine.download("RELIANCE", years=1)
        assert len(progress_calls) > 0

    def test_from_date_to_date(self):
        gw = _make_gateway()
        engine = HistoricalDownloadEngine(gw)
        df = engine.download(
            "RELIANCE",
            from_date="2026-01-01",
            to_date="2026-06-30",
        )
        assert not df.empty
