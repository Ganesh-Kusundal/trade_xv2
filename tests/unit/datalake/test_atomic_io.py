"""Tests for datalake.io — atomic file writes."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import pyarrow as pa
import pytest

from datalake.core.io import atomic_json_write, atomic_parquet_write, atomic_text_write


def _make_table(n: int = 5) -> pa.Table:
    df = pd.DataFrame(
        {
            "timestamp": pd.date_range("2026-01-01", periods=n, freq="1min"),
            "symbol": ["TEST"] * n,
            "close": [100.0 + i for i in range(n)],
        }
    )
    return pa.Table.from_pandas(df, preserve_index=False)


class TestAtomicParquetWrite:
    def test_writes_readable_parquet(self, tmp_path: Path) -> None:
        path = tmp_path / "data.parquet"
        table = _make_table()

        atomic_parquet_write(path, table, compression="snappy")

        assert path.exists()
        result = pd.read_parquet(path)
        assert len(result) == 5
        assert list(result.columns) == ["timestamp", "symbol", "close"]

    def test_no_tmp_left_behind(self, tmp_path: Path) -> None:
        path = tmp_path / "data.parquet"
        atomic_parquet_write(path, _make_table())

        assert not (tmp_path / "data.parquet.tmp").exists()

    def test_replaces_existing_file(self, tmp_path: Path) -> None:
        path = tmp_path / "data.parquet"
        old = pd.DataFrame({"a": [1, 2]})
        old.to_parquet(path, index=False)

        atomic_parquet_write(path, _make_table())

        result = pd.read_parquet(path)
        assert "a" not in result.columns

    def test_cleans_up_temp_on_failure(self, tmp_path: Path) -> None:
        path = tmp_path / "data.parquet"

        with (
            patch("datalake.core.io.pq.write_table", side_effect=RuntimeError("boom")),
            pytest.raises(RuntimeError, match="boom"),
        ):
            atomic_parquet_write(path, _make_table())

        assert not path.exists()
        assert not (tmp_path / "data.parquet.tmp").exists()


class TestAtomicTextWrite:
    def test_writes_text(self, tmp_path: Path) -> None:
        path = tmp_path / "config.txt"
        atomic_text_write(path, "hello world")

        assert path.read_text(encoding="utf-8") == "hello world"

    def test_no_tmp_left_behind(self, tmp_path: Path) -> None:
        path = tmp_path / "config.txt"
        atomic_text_write(path, "hello")

        assert not (tmp_path / "config.txt.tmp").exists()

    def test_replaces_existing(self, tmp_path: Path) -> None:
        path = tmp_path / "config.txt"
        path.write_text("old", encoding="utf-8")

        atomic_text_write(path, "new")

        assert path.read_text(encoding="utf-8") == "new"


class TestAtomicJsonWrite:
    def test_writes_json(self, tmp_path: Path) -> None:
        path = tmp_path / "data.json"
        atomic_json_write(path, {"key": "value", "number": 42})

        data = json.loads(path.read_text(encoding="utf-8"))
        assert data == {"key": "value", "number": 42}

    def test_no_tmp_left_behind(self, tmp_path: Path) -> None:
        path = tmp_path / "data.json"
        atomic_json_write(path, {"a": 1})

        assert not (tmp_path / "data.json.tmp").exists()
