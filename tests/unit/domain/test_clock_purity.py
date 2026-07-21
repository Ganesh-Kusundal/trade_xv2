"""Architecture guard — datetime.now()/utcnow() must not appear in fill/event paths.

All time-dependent code in broker mappers, fill engines, and event factories
must use ``get_current_clock().now()`` from ``domain.ports.time_service`` so
that virtual clocks work in tests and replay.
"""

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
FORBIDDEN_DIRS = [
    ROOT / "src/brokers/providers/paper",
    ROOT / "src/brokers/providers/upstox/mappers",
    ROOT / "src/brokers/providers/upstox/orders",
    ROOT / "src/brokers/providers/dhan/websocket",
    ROOT / "src/brokers/providers/dhan/data",
    ROOT / "src/domain/events",
    ROOT / "src/application/execution",
    ROOT / "src/application/oms/_internal",
    ROOT / "src/analytics/paper",
    ROOT / "src/analytics/replay",
    ROOT / "src/analytics/strategy",
    ROOT / "src/application/trading",
]
FORBIDDEN_FILES = [
    ROOT / "src/interface/api/routers/orders.py",
    ROOT / "src/interface/api/routers/_trades.py",
]
PATTERN = re.compile(r"datetime\.now\(|datetime\.utcnow\(")
ALLOWED_FILES = {"test_clock_purity.py", "__init__.py"}


def _scan_file(py: Path, violations: list[str]) -> None:
    if py.name in ALLOWED_FILES:
        return
    text = py.read_text(errors="ignore")
    for i, line in enumerate(text.splitlines(), 1):
        if PATTERN.search(line) and not line.strip().startswith("#"):
            rel = py.relative_to(ROOT)
            violations.append(f"  {rel}:{i}: {line.strip()}")


@pytest.mark.architecture
def test_no_datetime_now_in_fill_event_paths():
    violations = []
    for directory in FORBIDDEN_DIRS:
        if not directory.exists():
            continue
        for py in directory.rglob("*.py"):
            _scan_file(py, violations)
    for py in FORBIDDEN_FILES:
        if py.is_file():
            _scan_file(py, violations)
    if violations:
        pytest.fail(
            "datetime.now()/utcnow() found in fill/event paths (use get_current_clock().now()):\n"
            + "\n".join(violations)
        )
