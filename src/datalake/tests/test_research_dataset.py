from __future__ import annotations

import json
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from datalake.research.dataset import ResearchDataset


@pytest.fixture
def temp_root():
    with tempfile.TemporaryDirectory() as tmp:
        old = ResearchDataset.root
        ResearchDataset.root = Path(tmp) / "research_datasets"
        yield ResearchDataset.root
        ResearchDataset.root = old


def _make_curated_data(root: Path) -> None:
    curated = root / "curated" / "equities" / "candles" / "year=2026" / "month=01"
    curated.mkdir(parents=True, exist_ok=True)

    np.random.seed(42)
    dates = pd.date_range("2026-01-01", periods=20, freq="1h")
    symbols = ["RELIANCE", "TCS"]
    rows = []
    for sym in symbols:
        close = 100 + np.cumsum(np.random.randn(len(dates)) * 0.5)
        for i, ts in enumerate(dates):
            rows.append(
                {
                    "timestamp": ts,
                    "symbol": sym,
                    "exchange": "NSE",
                    "open": close[i] + np.random.randn() * 0.2,
                    "high": close[i] + abs(np.random.randn()) * 0.5,
                    "low": close[i] - abs(np.random.randn()) * 0.5,
                    "close": close[i],
                    "volume": int(np.random.randint(1000, 10000)),
                    "oi": 0,
                    "event_time": ts,
                    "published_at": ts + pd.Timedelta(seconds=1),
                    "ingested_at": pd.Timestamp.now(),
                    "is_correction": False,
                }
            )
    df = pd.DataFrame(rows)
    df.to_parquet(curated / "data_001.parquet", index=False, compression="snappy")


class TestCreateDataset:
    def test_metadata_contains_expected_fields(self, temp_root) -> None:
        market_root = temp_root.parent
        _make_curated_data(market_root)
        ResearchDataset.root = temp_root

        ds = ResearchDataset.create(
            universe="NIFTY50",
            as_of_date="2026-01-01",
            features=["atr_14", "sma_20"],
            date_from="2026-01-01",
            date_to="2026-01-02",
            timeframe="1h",
            curated_root=str(market_root / "curated"),
        )
        meta = ds.metadata
        for key in ("hash", "short_hash", "name", "universe", "as_of_date",
                     "features", "date_from", "date_to", "timeframe", "created_at",
                     "row_count", "symbol_count"):
            assert key in meta, f"Missing metadata key: {key}"
        assert "atr_14" in meta["features"]
        assert "sma_20" in meta["features"]

    def test_hash_is_deterministic(self, temp_root) -> None:
        market_root = temp_root.parent
        _make_curated_data(market_root)
        ResearchDataset.root = temp_root

        kwargs = {
            "universe": "NIFTY50",
            "as_of_date": "2026-01-01",
            "features": ["atr_14"],
            "date_from": "2026-01-01",
            "date_to": "2026-01-02",
            "timeframe": "1h",
            "curated_root": str(market_root / "curated"),
        }
        ds1 = ResearchDataset.create(**kwargs)
        ds2 = ResearchDataset.create(**kwargs)
        assert ds1.metadata["hash"] == ds2.metadata["hash"]
        assert ds1.metadata["short_hash"] == ds2.metadata["short_hash"]

    def test_dataset_is_frozen(self, temp_root) -> None:
        market_root = temp_root.parent
        _make_curated_data(market_root)
        ResearchDataset.root = temp_root

        ds = ResearchDataset.create(
            universe="NIFTY50",
            as_of_date="2026-01-01",
            features=["sma_20"],
            date_from="2026-01-01",
            date_to="2026-01-02",
            timeframe="1h",
            curated_root=str(market_root / "curated"),
        )
        df1 = ds.load()
        df2 = ds.load()
        assert df1.equals(df2)

        data_path = ds._path / "data.parquet"
        assert data_path.exists()

        meta_path = ds._path / "metadata.json"
        assert meta_path.exists()
        with open(meta_path) as f:
            meta = json.load(f)
        assert "created_at" in meta

    def test_list_datasets(self, temp_root) -> None:
        market_root = temp_root.parent
        _make_curated_data(market_root)
        ResearchDataset.root = temp_root

        ResearchDataset.create(
            universe="NIFTY50",
            as_of_date="2026-01-01",
            features=["atr_14"],
            date_from="2026-01-01",
            date_to="2026-01-02",
            timeframe="1h",
            curated_root=str(market_root / "curated"),
        )
        datasets = ResearchDataset.list()
        assert len(datasets) >= 1
        assert datasets[0]["features"] == ["atr_14"]


class TestLoadNonexistent:
    def test_load_nonexistent_raises(self, temp_root) -> None:
        ResearchDataset.root = temp_root
        with pytest.raises(FileNotFoundError):
            ResearchDataset.load_by_hash("deadbeef1234")

    def test_load_by_name_nonexistent_raises(self, temp_root) -> None:
        ResearchDataset.root = temp_root
        with pytest.raises(FileNotFoundError):
            ResearchDataset.load_by_name("nonexistent_dataset")
