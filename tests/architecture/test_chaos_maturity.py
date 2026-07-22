"""ADR-0013 Gate 3 — chaos suite maturity ratchets (R11)."""

from __future__ import annotations

from pathlib import Path

import pytest


_CHAOS_DIR = Path(__file__).resolve().parents[1] / "chaos"


@pytest.mark.architecture
def test_chaos_conftest_auto_marks_directory():
    conftest = _CHAOS_DIR / "conftest.py"
    assert conftest.is_file()
    src = conftest.read_text(encoding="utf-8")
    assert "pytest_collection_modifyitems" in src
    assert "pytest.mark.chaos" in src


@pytest.mark.architecture
def test_chaos_suite_has_test_modules():
    modules = sorted(_CHAOS_DIR.glob("test_*.py"))
    assert len(modules) >= 10, "expected a substantive chaos suite under tests/chaos/"


@pytest.mark.architecture
def test_reconciliation_chaos_has_no_tautological_drift_assertions():
    src = (_CHAOS_DIR / "test_reconciliation_failures.py").read_text(encoding="utf-8")
    assert "assert len(drift) >= 0" not in src


@pytest.mark.architecture
def test_chaos_green_artifact_writer_exists():
    script = Path(__file__).resolve().parents[2] / "scripts" / "ci" / "write_chaos_green_artifact.py"
    assert script.is_file()
    src = script.read_text(encoding="utf-8")
    assert "ADR-0013-3" in src
    assert "iso_week" in src
