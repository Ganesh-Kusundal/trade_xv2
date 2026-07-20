"""P5-T1 (drift D13): ban MagicMock / mock.patch on the order/gate/parity path.

The system trades real money. The live-order gate, the extended-order
executors, the broker gateways, and the parity gate are safety-critical
surfaces; their tests must exercise real protocol fakes (e.g. ``FakeHttpClient``,
a plain stub object), never ``MagicMock`` / ``unittest.mock.patch`` over the
order/gate/parity logic. A mock that silently returns ``None`` for an
unauthorized order is exactly the class of bug this remediation closes.

This test guards two things:

1. A small set of explicitly-named safety-path test files must stay
   mock-free (the original, strongest guarantee).
2. Every other test file whose path indicates it is on a safety-critical
   surface (order / gate / parity / broker / oms / execution / risk /
   kill-switch) and which was *previously* mock-free must stay mock-free.
   The clean baseline is recorded in ``_mock_safety_baseline.txt`` and is
   widened manually as files are cleaned. The guard fails the moment a mock
   is (re)introduced on a surface that was clean.

Adding a mock to one of these files must break CI, not the market.

Run with ``pytest tests/architecture/test_no_mock_in_integration.py``.
"""

from __future__ import annotations

from pathlib import Path

# Safety-critical test files (order / gate / parity surface). These must stay
# mock-free unconditionally. If you need a double, use a real protocol fake or
# a plain stub object with only the attributes the code reads — never MagicMock.
SAFETY_PATH_TESTS = [
    "tests/unit/application/oms/test_live_order_authority.py",
    "tests/unit/brokers/dhan/test_extended_order_gate.py",
    "tests/unit/brokers/upstox/test_exit_all_gate.py",
    "tests/unit/interface/api/test_require_live_broker.py",
    "tests/architecture/test_parity_gate_unbypassable.py",
]

# Path-keyword heuristic: a test file matching this pattern is on a
# safety-critical (money-trading) surface and is expected to be mock-free.
_SAFETY_SURFACE_RE = __import__("re").compile(
    r"(order|gate|parity|broker|kill_switch|risk|oms|execut|place_order|cancel)",
    __import__("re").IGNORECASE,
)

# Files that are not real test bodies and must never be scanned.
_NON_TEST = {"__init__.py", "conftest.py"}

_FORBIDDEN = (
    "MagicMock",
    "mock.patch",
    "unittest.mock",
    "patch(",
)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _has_mock(txt: str) -> bool:
    return any(tok in txt for tok in _FORBIDDEN)


def _test_root() -> Path:
    # This file lives in <repo>/tests/architecture/; the tests tree is the
    # parent of this file's directory.
    return Path(__file__).resolve().parent.parent


def _baseline() -> set[str]:
    path = Path(__file__).resolve().parent / "_mock_safety_baseline.txt"
    if not path.exists():
        return set()
    return {line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()}


def test_no_mocks_on_safety_path():
    """Hard guarantee: the named safety-path files must be mock-free."""
    root = _test_root()
    violations: list[tuple[str, int, str]] = []
    for rel in SAFETY_PATH_TESTS:
        path = root / rel
        if not path.exists():
            continue
        for lineno, line in enumerate(_read(path).splitlines(), start=1):
            if any(tok in line for tok in _FORBIDDEN):
                violations.append((rel, lineno, line.strip()))
    assert not violations, "Mocks forbidden on the order/gate/parity safety path:\n" + "\n".join(
        f"  {f}:{n}: {src}" for f, n, src in violations
    )


def test_no_mocks_introduced_on_clean_safety_surface():
    """Widened guard: any safety-surface test file recorded in the clean
    baseline must stay mock-free. Files are added to the baseline as they are
    cleaned, so the guard widens over time and never fails on currently-mocked
    files."""
    root = _test_root()
    clean = _baseline()
    violations: list[tuple[str, int, str]] = []
    for rel in sorted(clean):
        path = root / rel
        if not path.exists():
            # File moved/removed — baseline is stale; do not fail, but surface
            # via the assertion message below only when there are real hits.
            continue
        txt = _read(path)
        if _has_mock(txt):
            for lineno, line in enumerate(txt.splitlines(), start=1):
                if any(tok in line for tok in _FORBIDDEN):
                    violations.append((rel, lineno, line.strip()))
                    break
    assert not violations, (
        "Mocks introduced on a safety-critical (order/gate/parity/broker/oms) "
        "test surface that was previously clean (recorded in "
        "_mock_safety_baseline.txt):\n" + "\n".join(f"  {f}:{n}: {src}" for f, n, src in violations)
    )
