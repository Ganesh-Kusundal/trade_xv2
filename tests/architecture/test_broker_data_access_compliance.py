"""Architecture compliance — Layer 2 data access (no wire methods in interface/)."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
INTERFACE_ROOT = PROJECT_ROOT / "src" / "interface"

# Empty: interface/ must not call wire portfolio/quote shortcuts.
_WIRE_METHOD_ALLOWLIST: set[Path] = set()

_BANNED_WIRE_CALLS = re.compile(r"\.(?:ltp|quote|funds|positions|holdings)\s*\(")

_FACTORY_IMPORT = re.compile(
    r"from\s+brokers\.dhan\.identity\.factory\s+import|BrokerFactory\s*\(\s*\)\.create"
)


def _iter_py_files(root: Path) -> list[Path]:
    if not root.is_dir():
        return []
    return sorted(p for p in root.rglob("*.py") if p.is_file())


def _scan_wire_calls(path: Path) -> list[str]:
    if path in _WIRE_METHOD_ALLOWLIST:
        return []
    text = path.read_text(encoding="utf-8")
    hits: list[str] = []
    for i, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        if stripped.startswith("#") or stripped.startswith('"""') or stripped.startswith("'''"):
            continue
        if _BANNED_WIRE_CALLS.search(line):
            hits.append(f"{path.relative_to(PROJECT_ROOT)}:{i}: {stripped[:100]}")
    return hits


def _scan_factory_imports(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8")
    hits: list[str] = []
    for i, line in enumerate(text.splitlines(), start=1):
        if _FACTORY_IMPORT.search(line):
            hits.append(f"{path.relative_to(PROJECT_ROOT)}:{i}: {line.strip()[:100]}")
    return hits


@pytest.mark.architecture
class TestBrokerDataAccessCompliance:
    """interface/ must not call wire gateway market/portfolio shortcuts."""

    def test_interface_no_wire_ltp_quote_funds(self) -> None:
        violations: list[str] = []
        for path in _iter_py_files(INTERFACE_ROOT):
            violations.extend(_scan_wire_calls(path))
        assert not violations, "Wire method calls in interface/:\n" + "\n".join(violations)

    def test_interface_no_broker_factory_imports(self) -> None:
        violations: list[str] = []
        for path in _iter_py_files(INTERFACE_ROOT):
            violations.extend(_scan_factory_imports(path))
        assert not violations, "BrokerFactory bypass in interface/:\n" + "\n".join(violations)
