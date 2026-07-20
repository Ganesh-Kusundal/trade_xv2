"""Architecture test: datetime.now() forbidden in execution/risk/domain paths (I2).

The E2E spec (invariant I2) requires all order/trade/event timestamps to come
from an injected ClockPort. datetime.now() is forbidden in these paths to
ensure replay determinism.
"""

from __future__ import annotations

import ast
import pathlib

# Directories where datetime.now() is forbidden
FORBIDDEN_PATHS = [
    "src/application/execution/",
    "src/application/oms/",
    "src/domain/entities/",
    "src/domain/execution_contracts.py",
    "src/application/trading/trading_orchestrator.py",
]

# Allowed exceptions (clock implementations themselves)
ALLOWED_SUFFIXES = [
    "runtime/time_service.py",
    "domain/ports/time_service.py",
    "domain/ports/time_service_impls.py",
    "infrastructure/time/clock.py",
    "infrastructure/time_service.py",
]


def _find_datetime_now_calls(filepath: pathlib.Path) -> list[int]:
    """Find lines with datetime.now() calls using AST parsing."""
    try:
        tree = ast.parse(filepath.read_text())
    except (SyntaxError, UnicodeDecodeError):
        return []

    lines = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            # Check for datetime.now() pattern
            if (
                isinstance(node.func, ast.Attribute)
                and node.func.attr == "now"
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id == "datetime"
            ):
                lines.append(node.lineno)
    return lines


def _is_allowed_file(rel_path: str) -> bool:
    """Check if this file is an allowed clock implementation."""
    return any(rel_path.endswith(suffix) for suffix in ALLOWED_SUFFIXES)


def test_no_datetime_now_in_execution_paths():
    """datetime.now() is forbidden in execution/risk/domain timestamp paths."""
    violations = []
    root = pathlib.Path("src")

    for path_pattern in FORBIDDEN_PATHS:
        if path_pattern.endswith(".py"):
            filepath = root / path_pattern
            if filepath.exists():
                rel = path_pattern
                if not _is_allowed_file(rel):
                    lines = _find_datetime_now_calls(filepath)
                    if lines:
                        violations.append(f"{rel}:{lines}")
        else:
            dirpath = root / path_pattern
            if dirpath.exists():
                for py_file in dirpath.rglob("*.py"):
                    rel = str(py_file.relative_to(root))
                    if _is_allowed_file(rel):
                        continue
                    lines = _find_datetime_now_calls(py_file)
                    if lines:
                        violations.append(f"{rel}:{lines}")

    assert not violations, (
        "datetime.now() found in forbidden paths (I2 invariant):\n"
        + "\n".join(f"  - {v}" for v in violations)
        + "\n\nUse get_current_clock().now() or inject ClockPort instead."
    )
