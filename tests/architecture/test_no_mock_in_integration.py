"""P5-T1 (drift D13): ban MagicMock / mock.patch on the order/gate/parity path.

The system trades real money. The live-order gate, the extended-order
executors, and the parity gate are safety-critical surfaces; their tests must
exercise real protocol fakes (e.g. ``FakeHttpClient``, a plain stub object),
never ``MagicMock`` / ``unittest.mock.patch`` over the order/gate/parity logic.
A mock that silently returns ``None`` for an unauthorized order is exactly the
class of bug this remediation closes.

This test scans the safety-path test files and fails if any use
``MagicMock`` / ``mock.patch``. Adding a mock to one of these files must break
CI, not the market.
"""

from __future__ import annotations

from pathlib import Path

# Safety-critical test files (order / gate / parity surface). These must stay
# mock-free. If you need a double, use a real protocol fake or a plain stub
# object with only the attributes the code reads — never MagicMock.
SAFETY_PATH_TESTS = [
    "tests/unit/application/oms/test_live_order_authority.py",
    "tests/unit/brokers/dhan/test_extended_order_gate.py",
    "tests/unit/brokers/upstox/test_exit_all_gate.py",
    "tests/unit/interface/api/test_require_live_broker.py",
    "tests/architecture/test_parity_gate_unbypassable.py",
]

_FORBIDDEN = (
    "MagicMock",
    "mock.patch",
    "unittest.mock",
    "patch(",
)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_no_mocks_on_safety_path():
    root = Path(__file__).resolve().parent.parent.parent
    violations: list[tuple[str, int, str]] = []
    for rel in SAFETY_PATH_TESTS:
        path = root / rel
        if not path.exists():
            continue
        for lineno, line in enumerate(_read(path).splitlines(), start=1):
            if any(tok in line for tok in _FORBIDDEN):
                violations.append((rel, lineno, line.strip()))
    assert not violations, (
        "Mocks forbidden on the order/gate/parity safety path:\n"
        + "\n".join(f"  {f}:{n}: {src}" for f, n, src in violations)
    )
