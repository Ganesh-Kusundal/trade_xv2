"""Injectable parquet writer — composition root wires infrastructure/datalake impl."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

_ParquetWriter = Callable[..., None]
_writer: _ParquetWriter | None = None


def set_parquet_writer(writer: _ParquetWriter) -> None:
    """Register atomic parquet write (composition root)."""
    global _writer
    _writer = writer


def atomic_parquet_write(path: Path, table: Any, **write_options: Any) -> None:
    """Write parquet via the registered sink; raises if not wired."""
    if _writer is None:
        raise RuntimeError(
            "Parquet writer not registered. "
            "Call domain.ports.io.set_parquet_writer(...) at composition root."
        )
    _writer(path, table, **write_options)
