"""Atomic I/O utilities for the data lake.

All writes go to a sibling temp file, are fsync'd, then atomically renamed into
place so readers never observe a partial file.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq


def _temp_path(path: Path) -> Path:
    """Return a temp-file path next to the final destination."""
    return path.with_suffix(f"{path.suffix}.tmp")


def _fsync_and_replace(tmp_path: Path, final_path: Path) -> None:
    """Flush ``tmp_path`` to disk and atomically replace ``final_path``."""
    # Ensure parent directory exists (and is on the same filesystem as target).
    final_path.parent.mkdir(parents=True, exist_ok=True)

    # fsync the file content.
    with open(tmp_path, "rb") as fh:
        os.fsync(fh.fileno())

    # fsync the directory so the rename is durable.
    try:
        dir_fd = os.open(final_path.parent, os.O_RDONLY | os.O_DIRECTORY)
        os.fsync(dir_fd)
    finally:
        os.close(dir_fd)

    os.replace(tmp_path, final_path)


def atomic_parquet_write(path: Path, table: pa.Table, **write_options: Any) -> None:
    """Write a PyArrow Table to ``path`` atomically.

    Parameters
    ----------
    path : Path
        Destination Parquet file path.
    table : pa.Table
        Table to write.
    write_options : dict
        Extra options forwarded to ``pyarrow.parquet.write_table``.
    """
    tmp_path = _temp_path(path)
    try:
        pq.write_table(table, tmp_path, **write_options)
        _fsync_and_replace(tmp_path, path)
    except Exception:
        # Best-effort cleanup so we don't leave a corrupt temp file behind.
        if tmp_path.exists():
            tmp_path.unlink()
        raise


def atomic_text_write(path: Path, content: str) -> None:
    """Write ``content`` to ``path`` atomically as UTF-8 text."""
    tmp_path = _temp_path(path)
    try:
        tmp_path.write_text(content, encoding="utf-8")
        _fsync_and_replace(tmp_path, path)
    except Exception:
        if tmp_path.exists():
            tmp_path.unlink()
        raise


def atomic_json_write(path: Path, data: Any) -> None:
    """Serialize ``data`` as JSON and write it to ``path`` atomically."""
    atomic_text_write(path, json.dumps(data, indent=2, default=str))
