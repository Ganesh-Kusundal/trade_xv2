"""Soft god-class proxy: no src/ Python file exceeds 500 lines.

ponytail: LOC ceiling only. Upgrade: import/call-graph degree ≤ 50
(ADR-style) when a degree scanner exists.
"""

from __future__ import annotations

from pathlib import Path

_SRC = Path(__file__).resolve().parents[2] / "src"
_MAX_LINES = 500


def test_no_src_file_exceeds_500_lines() -> None:
    oversized: list[str] = []
    for path in sorted(_SRC.rglob("*.py")):
        n = sum(1 for _ in path.open(encoding="utf-8"))
        if n > _MAX_LINES:
            oversized.append(f"{path.relative_to(_SRC)}: {n} lines")
    assert not oversized, "god-class LOC ceiling exceeded:\n" + "\n".join(oversized)
