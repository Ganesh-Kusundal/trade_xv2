"""Architecture test: forbid broker string-branching in the composition root.

G1 (P5-1): the runtime/ composition root is the *only* place permitted to import
concrete broker packages, but it must never select a broker via a private-attribute
string branch such as ``bs._active_name == "dhan"`` or ``getattr(bs, "_active_name")``.
Broker selection is resolved through the ``BrokerService.active_broker`` /
``active_broker_name`` properties. This test locks that rule so the shotgun-surgery
coupling cannot regress.
"""

from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
RUNTIME_DIR = ROOT / "src" / "runtime"

# Patterns that constitute a broker string-branch (forbidden in src/runtime).
_FORBIDDEN = [
    ("_active_name string comparison", r"_\w*active_name\w*\s*[!=]="),
    ("getattr reach-through to _active_name", r'getattr\([^)]*["\']_active_name["\']'),
]


def _runtime_py_files() -> list[Path]:
    return sorted(p for p in RUNTIME_DIR.rglob("*.py") if "__pycache__" not in p.parts)


@pytest.mark.architecture
@pytest.mark.parametrize("label,pattern", _FORBIDDEN)
def test_no_broker_string_branch_in_runtime(label: str, pattern: str) -> None:
    """No private-attribute broker string branch may exist under src/runtime."""
    import re

    violations = []
    for path in _runtime_py_files():
        text = path.read_text(encoding="utf-8")
        # Strip `#` line comments so docstrings/comments can't trip the rule.
        code_only = "\n".join(line.split("#", 1)[0] for line in text.splitlines())
        for m in re.finditer(pattern, code_only):
            line_no = code_only.count("\n", 0, m.start()) + 1
            violations.append(f"  {path.relative_to(ROOT)}:{line_no}: {m.group(0)}")
    if violations:
        pytest.fail(f"{label} found in src/runtime/:\n" + "\n".join(violations))
