"""Architecture — Dhan domain module uses explicit imports, not __getattr__ (REF-12)."""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.mark.architecture
def test_dhan_domain_has_no_getattr_reexport() -> None:
    path = Path(__file__).resolve().parents[2] / "src" / "brokers" / "dhan" / "domain.py"
    source = path.read_text()
    assert "def __getattr__" not in source, "Use explicit domain imports in brokers/providers/dhan/domain.py"
