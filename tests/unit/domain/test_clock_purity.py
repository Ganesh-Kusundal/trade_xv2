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
    ROOT / "src/brokers/paper",
    ROOT / "src/brokers/upstox/mappers",
    ROOT / "src/brokers/upstox/orders",
    ROOT / "src/brokers/dhan/websocket",
    ROOT / "src/brokers/dhan/data",
    ROOT / "src/domain/events",
]
PATTERN = re.compile(r"datetime\.now\(|datetime\.utcnow\(")
ALLOWED_FILES = {"test_clock_purity.py", "__init__.py"}


@pytest.mark.architecture
def test_no_datetime_now_in_fill_event_paths():
    violations = []
    for directory in FORBIDDEN_DIRS:
        if not directory.exists():
            continue
        for py in directory.rglob("*.py"):
            if py.name in ALLOWED_FILES:
                continue
            text = py.read_text(errors="ignore")
            for i, line in enumerate(text.splitlines(), 1):
                if PATTERN.search(line) and not line.strip().startswith("#"):
                    rel = py.relative_to(ROOT)
                    violations.append(f"  {rel}:{i}: {line.strip()}")
    if violations:
        pytest.fail(
            "datetime.now()/utcnow() found in fill/event paths (use get_current_clock().now()):\n"
            + "\n".join(violations)
        )
