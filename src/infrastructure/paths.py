"""Resolve project root from any ``src/`` module path."""

from __future__ import annotations

from pathlib import Path


def project_root_from(module_file: str | Path, *, marker: str = "pyproject.toml") -> Path:
    """Walk parents until *marker* is found (usually repo root)."""
    here = Path(module_file).resolve()
    for parent in (here, *here.parents):
        if (parent / marker).is_file():
            return parent
    return here.parents[3]
