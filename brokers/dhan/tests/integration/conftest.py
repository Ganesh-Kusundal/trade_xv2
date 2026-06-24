"""Markers for Dhan live integration tests."""

from __future__ import annotations

from pathlib import Path

import pytest

_INTEGRATION_DIR = Path(__file__).resolve().parent


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    for item in items:
        if _INTEGRATION_DIR not in Path(str(item.fspath)).resolve().parents:
            continue
        item.add_marker(pytest.mark.integration)
        item.add_marker(pytest.mark.sandbox)

