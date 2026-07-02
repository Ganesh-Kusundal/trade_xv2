"""Tests for datalake.research — ResearchAPI."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from datalake.research.api import ResearchAPI


def _write_parquet(path: Path, df: pd.DataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(path, index=False)


def _make_canonical_df(
    n: int = 500,
    symbol: str = "TEST",
    start: str = "2026-01-01",
    freq: str = "1min",
) -> pd.DataFrame:
    np.random.seed(42)
    dates = pd.date_range(start, periods=n, freq=freq)
    close = 100 + np.cumsum(np.random.randn(n) * 0.5)
    return pd.DataFrame(
        {
            "timestamp": dates,
            "symbol": symbol,
            "exchange": "NSE",
            "open": close + np.random.randn(n) * 0.2,
            "high": close + np.abs(np.random.randn(n) * 0.5),
            "low": close - np.abs(np.random.randn(n) * 0.5),
            "close": close,
            "volume": np.random.randint(1000, 10000, n),
            "oi": np.zeros(n, dtype=np.int64),
        }
    )


def _setup_lake(tmp_path: Path, symbols: list[str] | None = None) -> None:
    """Set up a minimal data lake in tmp_path."""
    if symbols is None:
        symbols = ["RELIANCE", "TCS", "HDFCBANK"]

    for sym in symbols:
        df = _make_canonical_df(n=500, symbol=sym)
        parquet_path = (
            tmp_path / "equities" / "candles" / "timeframe=1m" / f"symbol={sym}" / "data.parquet"
        )
        _write_parquet(parquet_path, df)


class TestHistory:
    def test_loads_data(self, tmp_path: Path) -> None:
        _setup_lake(tmp_path, ["RELIANCE"])
        api = ResearchAPI(root=str(tmp_path))
        df = api.history("RELIANCE", years=5)
        assert len(df) == 500
        assert "close" in df.columns

    def test_missing_symbol_returns_empty(self, tmp_path: Path) -> None:
        _setup_lake(tmp_path)
        api = ResearchAPI(root=str(tmp_path))
        df = api.history("NONEXISTENT")
        assert df.empty

    def test_from_date_to_date(self, tmp_path: Path) -> None:
        _setup_lake(tmp_path, ["RELIANCE"])
        api = ResearchAPI(root=str(tmp_path))
        df = api.history("RELIANCE", from_date="2026-01-01 01:00", to_date="2026-01-01 04:00")
        assert len(df) > 0
        assert len(df) < 500

    def test_to_date_only(self, tmp_path: Path) -> None:
        _setup_lake(tmp_path, ["RELIANCE"])
        api = ResearchAPI(root=str(tmp_path))
        df = api.history("RELIANCE", to_date="2026-01-01 04:00")
        assert len(df) > 0
        assert len(df) < 500

    def test_years_filter(self, tmp_path: Path) -> None:
        _setup_lake(tmp_path, ["RELIANCE"])
        api = ResearchAPI(root=str(tmp_path))
        df_1yr = api.history("RELIANCE", years=1)
        df_5yr = api.history("RELIANCE", years=5)
        # 1 year should have fewer rows than 5 years
        assert len(df_1yr) <= len(df_5yr)


class TestUniverse:
    def test_loads_all_symbols(self, tmp_path: Path) -> None:
        _setup_lake(tmp_path, ["RELIANCE", "TCS", "HDFCBANK"])

        # Create universe CSV
        universe_dir = tmp_path / "data" / "universes"
        universe_dir.mkdir(parents=True)
        csv_path = universe_dir / "TEST.csv"
        pd.DataFrame({"symbol": ["RELIANCE", "TCS", "HDFCBANK"]}).to_csv(csv_path, index=False)

        # Patch UNIVERSE_FILES
        from datalake.schema import UNIVERSE_FILES

        UNIVERSE_FILES["TEST"] = str(csv_path)

        api = ResearchAPI(root=str(tmp_path))
        data = api.universe("TEST", lookback_days=365)
        assert len(data) == 3
        assert "RELIANCE" in data
        assert "TCS" in data

    def test_skips_missing_symbols(self, tmp_path: Path) -> None:
        _setup_lake(tmp_path, ["RELIANCE"])

        universe_dir = tmp_path / "data" / "universes"
        universe_dir.mkdir(parents=True)
        csv_path = universe_dir / "TEST.csv"
        pd.DataFrame({"symbol": ["RELIANCE", "NONEXISTENT"]}).to_csv(csv_path, index=False)

        from datalake.schema import UNIVERSE_FILES

        UNIVERSE_FILES["TEST"] = str(csv_path)

        api = ResearchAPI(root=str(tmp_path))
        data = api.universe("TEST", lookback_days=365)
        assert len(data) == 1
        assert "RELIANCE" in data


class TestScan:
    def test_lists_available_symbols(self, tmp_path: Path) -> None:
        _setup_lake(tmp_path, ["RELIANCE", "TCS"])

        universe_dir = tmp_path / "data" / "universes"
        universe_dir.mkdir(parents=True)
        csv_path = universe_dir / "TEST.csv"
        pd.DataFrame({"symbol": ["RELIANCE", "TCS", "HDFCBANK"]}).to_csv(csv_path, index=False)

        from datalake.schema import UNIVERSE_FILES

        UNIVERSE_FILES["TEST"] = str(csv_path)

        api = ResearchAPI(root=str(tmp_path))
        available = api.scan("TEST")
        assert "RELIANCE" in available
        assert "TCS" in available
        assert "HDFCBANK" not in available


class TestLatest:
    def test_returns_n_rows(self, tmp_path: Path) -> None:
        _setup_lake(tmp_path, ["RELIANCE"])
        api = ResearchAPI(root=str(tmp_path))
        df = api.latest("RELIANCE", n=5)
        assert len(df) == 5

    def test_latest_empty_for_missing(self, tmp_path: Path) -> None:
        _setup_lake(tmp_path)
        api = ResearchAPI(root=str(tmp_path))
        df = api.latest("NONEXISTENT")
        assert df.empty


class TestListAvailableSymbols:
    def test_lists_all_parquet_symbols(self, tmp_path: Path) -> None:
        _setup_lake(tmp_path, ["AAA", "BBB", "CCC"])
        api = ResearchAPI(root=str(tmp_path))
        symbols = api.list_available_symbols()
        assert "AAA" in symbols
        assert "BBB" in symbols
        assert "CCC" in symbols
        assert symbols == sorted(symbols)

    def test_empty_when_no_data(self, tmp_path: Path) -> None:
        api = ResearchAPI(root=str(tmp_path))
        symbols = api.list_available_symbols()
        assert symbols == []
