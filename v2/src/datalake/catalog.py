"""File-backed JSONL DataCatalog — Parquet-free Phase 5 store.

ponytail: JSONL per symbol under {root}/bars/{symbol}.jsonl.
Ceiling: no SQL engine / columnar scan — upgrade path is DuckDB+Parquet.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any


def _parse_ts(value: str | datetime) -> datetime:
    if isinstance(value, datetime):
        return value
    # fromisoformat handles +00:00; strip Z if present
    text = value.replace("Z", "+00:00")
    return datetime.fromisoformat(text)


def _safe_symbol(symbol: str) -> str:
    return symbol.replace("/", "_").replace(":", "_")


class DataCatalog:
    """Minimal bar catalog: write_bars / read_bars / query_bars over JSONL."""

    def __init__(self, root: str | Path) -> None:
        self._root = Path(root)
        self._bars_dir = self._root / "bars"
        self._bars_dir.mkdir(parents=True, exist_ok=True)

    def _path(self, symbol: str) -> Path:
        return self._bars_dir / f"{_safe_symbol(symbol)}.jsonl"

    def write_bars(self, symbol: str, bars: list[dict[str, Any]]) -> None:
        path = self._path(symbol)
        with path.open("a", encoding="utf-8") as fh:
            for bar in bars:
                fh.write(json.dumps(bar, default=str) + "\n")

    def read_bars(
        self,
        symbol: str,
        start: datetime,
        end: datetime,
    ) -> list[dict[str, Any]]:
        path = self._path(symbol)
        if not path.exists():
            return []
        out: list[dict[str, Any]] = []
        with path.open(encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                row = json.loads(line)
                ts = _parse_ts(row["timestamp"])
                if start <= ts <= end:
                    out.append(row)
        out.sort(key=lambda r: _parse_ts(r["timestamp"]))
        return out

    def query_bars(
        self,
        symbol: str,
        start: datetime,
        end: datetime,
    ) -> list[dict[str, Any]]:
        """SQL-like filter alias for read_bars (MCP / research callers)."""
        return self.read_bars(symbol, start, end)

    def has_bars(self, symbol: str) -> bool:
        path = self._path(symbol)
        return path.exists() and path.stat().st_size > 0
