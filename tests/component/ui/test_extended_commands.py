"""Offline smoke tests for extended CLI command modules."""

from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]


def test_extended_orders_module_exists() -> None:
    path = PROJECT_ROOT / "src/interface/ui/commands/extended_orders.py"
    assert path.exists()
    source = path.read_text(encoding="utf-8")
    assert "def super_order" in source or "def gtt_order" in source or "class" in source
