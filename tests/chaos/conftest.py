"""Chaos suite — auto-mark every test in this directory (ADR-0013 Gate 3)."""

from __future__ import annotations

from pathlib import Path

import pytest

_CHAOS_ROOT = Path(__file__).resolve().parent


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    for item in items:
        try:
            path = Path(str(item.fspath))
        except (AttributeError, TypeError):
            continue
        if _CHAOS_ROOT in path.parents or path.parent == _CHAOS_ROOT:
            item.add_marker(pytest.mark.chaos)
