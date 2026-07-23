"""SourceSelectionPolicy prefers local datalake then remote broker."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from datalake.catalog import DataCatalog
from datalake.source_selection import SourceSelectionPolicy
from domain.policies.source_selection import DataSourceKind
from domain.value_objects import InstrumentId, TimeFrame


def test_prefer_local_when_bars_exist(tmp_path: Path) -> None:
    catalog = DataCatalog(tmp_path)
    catalog.write_bars(
        "RELIANCE",
        [
            {
                "timestamp": "2024-01-15T00:00:00+00:00",
                "open": 100,
                "high": 105,
                "low": 99,
                "close": 104,
                "volume": 1000,
            }
        ],
    )
    policy = SourceSelectionPolicy(catalog)
    kind = policy.select(InstrumentId.parse("NSE:RELIANCE"), TimeFrame(value="1d"))
    assert kind is DataSourceKind.DATALAKE


def test_prefer_remote_when_local_empty(tmp_path: Path) -> None:
    policy = SourceSelectionPolicy(DataCatalog(tmp_path))
    kind = policy.select(InstrumentId.parse("NSE:TCS"), TimeFrame(value="1d"))
    assert kind is DataSourceKind.BROKER_HISTORICAL
