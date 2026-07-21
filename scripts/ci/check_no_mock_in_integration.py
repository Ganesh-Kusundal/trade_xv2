#!/usr/bin/env python3
"""Ban MagicMock on safety-critical test surfaces (replaces architecture pytest).

1. Named SAFETY_PATH_TESTS must stay mock-free unconditionally.
2. Files listed in tests/architecture/_mock_safety_baseline.txt that were
   previously clean must stay mock-free (ratchet; widen baseline as cleaned).
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TESTS = ROOT / "tests"
BASELINE = ROOT / "tests" / "architecture" / "_mock_safety_baseline.txt"

SAFETY_PATH_TESTS = (
    "tests/unit/application/oms/test_live_order_authority.py",
    "tests/unit/brokers/dhan/test_extended_order_gate.py",
    "tests/unit/brokers/upstox/test_exit_all_gate.py",
    "tests/unit/interface/api/test_require_live_broker.py",
    "tests/architecture/test_parity_gate_unbypassable.py",
)

_FORBIDDEN = ("MagicMock", "mock.patch", "unittest.mock", "patch(")


def _has_mock(text: str) -> bool:
    return any(tok in text for tok in _FORBIDDEN)


def _mock_hits(rel: str, text: str) -> list[str]:
    hits: list[str] = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        if any(tok in line for tok in _FORBIDDEN):
            hits.append(f"{rel}:{lineno}: {line.strip()}")
    return hits


def _baseline() -> set[str]:
    if not BASELINE.exists():
        return set()
    return {line.strip() for line in BASELINE.read_text(encoding="utf-8").splitlines() if line.strip()}


def main() -> int:
    violations: list[str] = []

    for rel in SAFETY_PATH_TESTS:
        path = ROOT / rel
        if not path.exists():
            continue
        violations.extend(_mock_hits(rel, path.read_text(encoding="utf-8")))

    for rel in sorted(_baseline()):
        path = ROOT / rel
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
        if _has_mock(text):
            violations.extend(_mock_hits(rel, text)[:1])

    if violations:
        print(
            "Mocks forbidden on order/gate/parity safety path "
            "(or reintroduced on baseline-clean surface):\n"
            + "\n".join(violations[:40]),
            file=sys.stderr,
        )
        return 1

    print("OK: safety-path + baseline-clean surfaces remain mock-free")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
