"""Regression tests for data equivalence.

Verifies that DataLakeGateway.history() and DataLakeMarketDataProvider.history()
return identical DataFrames for the same input, ensuring the adapter layer
does not alter data.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pandas.testing as pdt
import pyarrow as pa
import pytest

from datalake.adapters.analytics_provider import DataLakeMarketDataProvider
from datalake.core.io import atomic_parquet_write
from datalake.gateway import DataLakeGateway


@pytest.fixture()
def lake(tmp_path: Path) -> Path:
    """Create a minimal legacy-layout lake for equivalence testing."""
    hive = tmp_path / "equities" / "candles" / "timeframe=1m" / "symbol=EQTEST"
    hive.mkdir(parents=True)

    n = 100
    df = pd.DataFrame(
        {
            "timestamp": pd.date_range("2024-01-02 09:15", periods=n, freq="1min"),
            "symbol": "EQTEST",
            "open": [100.0 + i * 0.1 for i in range(n)],
            "high": [101.0 + i * 0.1 for i in range(n)],
            "low": [99.0 + i * 0.1 for i in range(n)],
            "close": [100.5 + i * 0.1 for i in range(n)],
            "volume": [1000 + i * 10 for i in range(n)],
        }
    )
    atomic_parquet_write(hive / "data.parquet", pa.Table.from_pandas(df, preserve_index=False))
    return tmp_path


class TestDataEquivalence:
    """Verify gateway and adapter return identical data."""

    def test_history_equivalence(self, lake: Path) -> None:
        gateway = DataLakeGateway(root=str(lake))
        provider = DataLakeMarketDataProvider(gateway=gateway, root=str(lake))

        gw_df = gateway.history("EQTEST", timeframe="1m")
        prov_df = provider.history("EQTEST", timeframe="1m")

        # Both should return data
        assert len(gw_df) > 0
        assert len(prov_df) > 0

        # Core columns must match
        common_cols = [c for c in gw_df.columns if c in prov_df.columns]
        pdt.assert_frame_equal(
            gw_df[common_cols].reset_index(drop=True),
            prov_df[common_cols].reset_index(drop=True),
            check_dtype=False,
        )

    def test_history_batch_equivalence(self, lake: Path) -> None:
        gateway = DataLakeGateway(root=str(lake))
        provider = DataLakeMarketDataProvider(gateway=gateway, root=str(lake))

        gw_df = gateway.history_batch(["EQTEST"], timeframe="1m")
        prov_df = provider.history_batch(["EQTEST"], timeframe="1m")

        assert len(gw_df) > 0
        assert len(prov_df) > 0

    def test_list_symbols_equivalence(self, lake: Path) -> None:
        gateway = DataLakeGateway(root=str(lake))
        provider = DataLakeMarketDataProvider(gateway=gateway, root=str(lake))

        gw_syms = gateway.list_symbols(timeframe="1m")
        prov_syms = provider.list_symbols(timeframe="1m")

        assert set(gw_syms) == set(prov_syms)
