"""Float / shares-outstanding data — load and query per-symbol fundamentals.

Sourced from yfinance (see scripts/sync_float_data.py) into a CSV cache,
mirroring how src/analytics/sector/mapping.py loads sector data.

Usage:
    provider = FloatDataProvider.default()
    row = provider.get("RELIANCE")  # {"float_shares": ..., "market_cap": ..., ...}
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from domain.symbols import normalize_symbol

_DEFAULT_CSV = Path("data/fundamentals/float_data.csv")


@dataclass
class FloatDataProvider:
    """Maps stock symbols to float/shares-outstanding fundamentals."""

    _data: dict[str, dict] = field(default_factory=dict)

    @classmethod
    def load_csv(cls, path: str | Path) -> FloatDataProvider:
        """Load float data from a CSV written by scripts/sync_float_data.py."""
        df = pd.read_csv(path)
        data = {
            str(row["symbol"]).upper(): row.drop("symbol").to_dict()
            for _, row in df.iterrows()
        }
        return cls(_data=data)

    @classmethod
    def default(cls) -> FloatDataProvider:
        """Load the on-disk float data cache, or an empty provider if absent."""
        if _DEFAULT_CSV.exists():
            return cls.load_csv(_DEFAULT_CSV)
        return cls()

    def get(self, symbol: str) -> dict | None:
        """Return the float/shares data for a symbol, or None if unknown."""
        row = self._data.get(normalize_symbol(symbol))
        return dict(row) if row is not None else None

    @property
    def total_symbols(self) -> int:
        return len(self._data)
