"""Architecture ratchet — interface layer must not import brokers.* directly."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
INTERFACE = ROOT / "src" / "interface"

_BROKERS_IMPORT = re.compile(
    r"^\s*(from\s+brokers[\w.]*\s+import|import\s+brokers[\w.]*)",
    re.MULTILINE,
)


def _interface_py_files() -> list[Path]:
    return sorted(INTERFACE.rglob("*.py"))


def test_no_direct_brokers_imports_in_interface() -> None:
    offenders: list[str] = []
    for path in _interface_py_files():
        text = path.read_text(encoding="utf-8")
        if _BROKERS_IMPORT.search(text):
            offenders.append(path.relative_to(ROOT).as_posix())
    assert not offenders, (
        "interface/ must not import brokers.* — use runtime.platform_bridge or "
        f"broker_ops: {offenders}"
    )
