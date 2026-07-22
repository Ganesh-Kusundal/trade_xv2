"""Mid-history trading-day gap detection and repair in repair_missing phase B."""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import pandas as pd

from datalake.core.nse_calendar import is_trading_day, trading_days_between
from datalake.ingestion.loader import HistoricalDataLoader
from tests.unit.datalake.test_loader_merge import FakeGateway, _candles


def _write_daily_bars(loader: HistoricalDataLoader, symbol: str, days: list[date]) -> None:
    dates = [f"{d.isoformat()} 09:15:00" for d in days]
    df = _candles(dates, base_price=100.0)
    df["symbol"] = symbol
    gw = FakeGateway(df)
    loader.download_symbol(symbol, gw, years=1, timeframe="1d", exchange="NSE")


class TestDetectInternalGapRanges:
    def test_finds_missing_trading_day_in_middle(self, tmp_path: Path) -> None:
        loader = HistoricalDataLoader(root=str(tmp_path))
        today = date.today()
        trading = trading_days_between(today - timedelta(days=14), today)
        assert len(trading) >= 3
        gap_day = trading[len(trading) // 2]
        present = [d for d in trading if d != gap_day]
        _write_daily_bars(loader, "RELIANCE", present)

        ranges = loader.detect_internal_gap_ranges("RELIANCE", timeframe="1d")
        assert ranges == [(gap_day, gap_day)]
        assert is_trading_day(gap_day)


class TestRepairInternalGaps:
    def test_tail_only_skips_internal_gap_fetch(self, tmp_path: Path) -> None:
        loader = HistoricalDataLoader(root=str(tmp_path))
        today = date.today()
        trading = trading_days_between(today - timedelta(days=14), today)
        gap_day = trading[len(trading) // 2]
        present = [d for d in trading if d != gap_day]
        _write_daily_bars(loader, "RELIANCE", present)

        def fetch_fn(symbol: str, exchange: str, timeframe: str, lookback_days: int) -> pd.DataFrame:
            raise AssertionError("tail-only sync must not fetch when tail is current")

        rows = loader.repair_missing(
            "RELIANCE", timeframe="1d", fetch_fn=fetch_fn, repair_scope="tail"
        )
        assert rows == 0
        assert loader.detect_internal_gap_ranges("RELIANCE", timeframe="1d") == [(gap_day, gap_day)]

    def test_fetches_missing_middle_day_and_preserves_surrounding_history(
        self, tmp_path: Path
    ) -> None:
        loader = HistoricalDataLoader(root=str(tmp_path))
        today = date.today()
        trading = trading_days_between(today - timedelta(days=14), today)
        gap_day = trading[len(trading) // 2]
        present = [d for d in trading if d != gap_day]
        _write_daily_bars(loader, "RELIANCE", present)

        path = (
            tmp_path
            / "equities"
            / "candles"
            / "timeframe=1d"
            / "symbol=RELIANCE"
            / "data.parquet"
        )
        before_count = len(pd.read_parquet(path))
        before_dates = set(pd.to_datetime(pd.read_parquet(path)["timestamp"]).dt.date)

        fetch_calls: list[int] = []

        def fetch_fn(symbol: str, exchange: str, timeframe: str, lookback_days: int) -> pd.DataFrame:
            fetch_calls.append(lookback_days)
            return _candles([f"{gap_day.isoformat()} 09:15:00"], base_price=150.0)

        rows = loader.repair_missing("RELIANCE", timeframe="1d", fetch_fn=fetch_fn, repair_scope="all")
        assert rows > 0
        assert fetch_calls, "expected at least one fetch for gap repair"

        after = pd.read_parquet(path)
        assert len(after) >= before_count
        after_dates = set(pd.to_datetime(after["timestamp"]).dt.date)
        assert gap_day in after_dates
        assert before_dates.issubset(after_dates)
