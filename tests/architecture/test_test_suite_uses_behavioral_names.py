"""Test files must name guarantees, not implementation history."""

from __future__ import annotations

from pathlib import Path

import pytest

# Filenames that encode sprint/phase/ticket history instead of behavior.
_FORBIDDEN_SUBSTRINGS = (
    "phase0",
    "phase1",
    "phase2",
    "phase3",
    "phase4",
    "phase5",
    "phase6",
    "phase7",
    "phase_",
    "_b7_",
    "b7_",
    "remediation_",
    "after_refactor",
    "new_feature",
    "issue_",
    "sprint_",
    "wave_",
    "fix_bug",
)

_ROOT = Path(__file__).resolve().parents[2]


def _test_files() -> list[Path]:
    files: list[Path] = []
    for base in (_ROOT / "tests", _ROOT / "src"):
        if not base.is_dir():
            continue
        for path in base.rglob("test_*.py"):
            if "__pycache__" in path.parts:
                continue
            files.append(path)
    return files


def test_no_history_encoded_test_filenames() -> None:
    """Reject test_*.py names that describe tickets/phases rather than behavior."""
    offenders: list[str] = []
    for path in _test_files():
        name = path.name.lower()
        for token in _FORBIDDEN_SUBSTRINGS:
            if token in name:
                offenders.append(f"{path.relative_to(_ROOT)} (matched {token!r})")
                break
    assert not offenders, (
        "Rename history-named tests to behavioral contracts (see tests/README.md):\n"
        + "\n".join(offenders)
    )


def test_pyramid_directories_exist() -> None:
    """Top-level pyramid layout is present under tests/."""
    for name in ("unit", "component", "integration", "e2e", "architecture"):
        assert (_ROOT / "tests" / name).is_dir(), f"missing tests/{name}"
