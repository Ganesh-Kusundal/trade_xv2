"""DataCatalog write/read roundtrip on a real tmp_path — no mocks."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from datalake.catalog import DataCatalog


def _bar(ts: str, o: float = 100.0, h: float = 110.0, low: float = 95.0, c: float = 105.0, v: int = 1000) -> dict:
    return {
        "timestamp": ts,
        "open": o,
        "high": h,
        "low": low,
        "close": c,
        "volume": v,
    }


def test_write_read_roundtrip(tmp_path: Path) -> None:
    catalog = DataCatalog(tmp_path)
    bars = [
        _bar("2024-01-15T09:15:00+00:00", 100, 105, 99, 104, 1000),
        _bar("2024-01-16T09:15:00+00:00", 104, 108, 103, 107, 1200),
        _bar("2024-01-17T09:15:00+00:00", 107, 110, 106, 109, 900),
    ]
    catalog.write_bars("RELIANCE", bars)

    got = catalog.read_bars(
        "RELIANCE",
        start=datetime(2024, 1, 15, tzinfo=UTC),
        end=datetime(2024, 1, 17, 23, 59, 59, tzinfo=UTC),
    )
    assert len(got) == 3
    assert got[0]["close"] == 104
    assert got[-1]["close"] == 109


def test_read_bars_filters_range(tmp_path: Path) -> None:
    catalog = DataCatalog(tmp_path)
    catalog.write_bars(
        "TCS",
        [
            _bar("2024-01-10T00:00:00+00:00", c=1),
            _bar("2024-01-15T00:00:00+00:00", c=2),
            _bar("2024-01-20T00:00:00+00:00", c=3),
        ],
    )
    got = catalog.read_bars(
        "TCS",
        start=datetime(2024, 1, 12, tzinfo=UTC),
        end=datetime(2024, 1, 18, tzinfo=UTC),
    )
    assert len(got) == 1
    assert got[0]["close"] == 2


def test_query_bars_alias(tmp_path: Path) -> None:
    catalog = DataCatalog(tmp_path)
    catalog.write_bars("INFY", [_bar("2024-02-01T00:00:00+00:00", c=42)])
    got = catalog.query_bars(
        "INFY",
        start=datetime(2024, 1, 1, tzinfo=UTC),
        end=datetime(2024, 12, 31, tzinfo=UTC),
    )
    assert len(got) == 1
    assert got[0]["close"] == 42


def test_missing_symbol_returns_empty(tmp_path: Path) -> None:
    catalog = DataCatalog(tmp_path)
    got = catalog.read_bars(
        "NOPE",
        start=datetime(2024, 1, 1, tzinfo=UTC),
        end=datetime(2024, 12, 31, tzinfo=UTC),
    )
    assert got == []
