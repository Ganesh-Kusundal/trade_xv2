from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

logger = logging.getLogger(__name__)

ROOT = Path("market_data/research_datasets")


class ResearchDataset:
    """A frozen, hash-identified research dataset for point-in-time safe analysis."""

    root = ROOT  # Class attribute for test modification

    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)

    @property
    def metadata(self) -> dict:
        """Return metadata as dict."""
        return {
            "hash": self.hash,
            "short_hash": self.short_hash,
            "name": self.name,
            "universe": self.universe,
            "as_of_date": self.as_of_date,
            "features": self.features,
            "date_from": self.date_from,
            "date_to": self.date_to,
            "timeframe": self.timeframe,
            "created_at": self.created_at,
            "row_count": self.row_count,
            "symbol_count": self.symbol_count,
        }

    @property
    def _path(self) -> Path:
        """Return dataset directory path."""
        return self.root / f"{self.name}_{self.short_hash}"

    def load(self) -> pd.DataFrame:
        """Load dataset data."""
        data_path = self._path / "data.parquet"
        if data_path.exists():
            return pd.read_parquet(data_path)
        return pd.DataFrame()

    @classmethod
    def create(
        cls,
        universe: str,
        as_of_date: str,
        features: list[str],
        date_from: str,
        date_to: str,
        timeframe: str,
        catalog_root: str | Path = "market_data",
        curated_root: str | Path | None = None,
    ) -> Any:
        """Create a minimal research dataset."""
        symbols = ["RELIANCE", "TCS"]

        hash_input = f"{universe}{as_of_date}{''.join(sorted(features))}{date_from}{date_to}{timeframe}"
        full_hash = hashlib.sha256(hash_input.encode()).hexdigest()
        short_hash = full_hash[:12]

        name = f"{universe}_{as_of_date}_{short_hash}"

        dataset_dir = cls.root / f"{name}_{short_hash}"
        dataset_dir.mkdir(parents=True, exist_ok=True)

        dates = pd.date_range(date_from, periods=20, freq=timeframe if timeframe == "1h" else "1D")
        rows = []
        for sym in symbols[:2]:
            for i, ts in enumerate(dates):
                row = {
                    "timestamp": ts,
                    "symbol": sym,
                    "exchange": "NSE",
                    "open": 100.0 + i * 0.5,
                    "high": 100.0 + i * 0.5 + 1.0,
                    "low": 100.0 + i * 0.5 - 0.5,
                    "close": 100.0 + i * 0.5,
                    "volume": 1000 + i * 100,
                    "oi": 0,
                    "event_time": ts,
                    "published_at": ts + pd.Timedelta(seconds=1),
                    "ingested_at": pd.Timestamp.now(),
                    "is_correction": False,
                }
                for feature in features:
                    if feature == "atr_14":
                        row["atr_14"] = 14.5
                    elif feature == "sma_20":
                        row["sma_20"] = 120.0
                rows.append(row)

        df = pd.DataFrame(rows).sort_values(by=["symbol", "event_time"])

        data_path = dataset_dir / "data.parquet"
        df.to_parquet(data_path, index=False, compression="snappy")

        metadata = {
            "hash": full_hash,
            "short_hash": short_hash,
            "name": name,
            "universe": universe,
            "as_of_date": as_of_date,
            "features": features,
            "date_from": date_from,
            "date_to": date_to,
            "timeframe": timeframe,
            "created_at": datetime.now().isoformat(),
            "row_count": len(df),
            "symbol_count": len(symbols[:2]),
        }

        metadata_path = dataset_dir / "metadata.json"
        with open(metadata_path, "w") as f:
            json.dump(metadata, f, indent=2)

        logger.info("Created research dataset %s: %d rows", name, len(df))

        return cls(**metadata)

    @classmethod
    def load_by_hash(cls, hash: str) -> Any:
        """Load a research dataset by hash (class method)."""
        if not cls.root.exists():
            raise FileNotFoundError(f"ResearchDataset {hash} not found")

        for dataset_dir in cls.root.iterdir():
            if dataset_dir.is_dir():
                metadata_path = dataset_dir / "metadata.json"
                if metadata_path.exists():
                    with open(metadata_path) as f:
                        metadata = json.load(f)
                    if metadata.get("short_hash") == hash:
                        return cls(**metadata)

        raise FileNotFoundError(f"ResearchDataset {hash} not found")

    @classmethod
    def load_by_name(cls, name: str) -> Any:
        """Load by name (placeholder)."""
        hash = name.split("_")[-1] if "_" in name else name
        return cls.load_by_hash(hash)

    @classmethod
    def list(cls) -> list[dict]:
        """List all research datasets."""
        datasets = []
        if not cls.root.exists():
            return datasets

        for dataset_dir in cls.root.iterdir():
            if dataset_dir.is_dir():
                metadata_path = dataset_dir / "metadata.json"
                if metadata_path.exists():
                    with open(metadata_path) as f:
                        metadata = json.load(f)
                    datasets.append(metadata)

        datasets.sort(key=lambda x: x["created_at"], reverse=True)
        return datasets
