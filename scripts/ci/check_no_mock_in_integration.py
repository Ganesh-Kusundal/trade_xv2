#!/usr/bin/env python3
"""Ban MagicMock on safety-critical test surfaces (architecture gate → CI)."""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TESTS = ROOT / "tests"

SAFETY_PATH_TESTS = {
    "tests/unit/application/oms/test_live_order_authority.py",
    "tests/unit/brokers/dhan/test_extended_order_gate.py",
    "tests/unit/brokers/upstox/test_exit_all_gate.py",
    "tests/unit/interface/api/test_require_live_broker.py",
    "tests/architecture/test_parity_gate_unbypassable.py",
}

_SAFETY_SURFACE_RE = re.compile(
    r"(order|gate|parity|broker|kill_switch|risk|oms|execut|place_order|cancel)",
    re.IGNORECASE,
)

_FORBIDDEN = ("MagicMock", "mock.patch", "unittest.mock", "patch(")
_NON_TEST = {"__init__.py", "conftest.py"}


def _scan_file(rel: str, text: str) -> list[str]:
    if rel in SAFETY_PATH_TESTS or _SAFETY_SURFACE_RE.search(rel):
        hits = [tok for tok in _FORBIDDEN if tok in text]
        if hits:
            return [f"{rel}: contains {', '.join(hits)}"]
    return []


def main() -> int:
    violations: list[str] = []
    for path in TESTS.rglob("*.py"):
        if path.name in _NON_TEST:
            continue
        rel = path.relative_to(ROOT).as_posix()
        violations.extend(_scan_file(rel, path.read_text(encoding="utf-8")))
    if violations:
        print("\n".join(violations[:40]), file=sys.stderr)
        return 1
    print("OK: no forbidden mocks on safety-critical test surfaces")
    return 0


if __name__ == "__main__":
    sys.exit(main())
