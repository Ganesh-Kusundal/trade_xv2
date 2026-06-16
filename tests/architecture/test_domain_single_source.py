"""Architecture tests — prove domain types have a single source of truth.

These tests FAIL before the Sprint 1 refactoring and PASS after.
They use AST inspection to find class definitions, not just imports.

Design note (Dr. V): "A test that proves your architecture is broken
is more valuable than a test that proves your feature works. The
feature test catches a regression; the architecture test catches a
design debt that will cause a hundred future bugs."
"""

from __future__ import annotations

import ast
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_BROKERS_DIR = _PROJECT_ROOT / "brokers"

_CANONICAL_TYPES = {"Quote", "Balance", "DepthLevel", "MarketDepth"}

_CANONICAL_PACKAGE = "brokers/common/core"


def _find_class_definitions(
    root: Path, class_names: set[str]
) -> list[tuple[Path, str]]:
    """Walk Python files under root, return (file, class_name) for definitions."""
    hits: list[tuple[Path, str]] = []
    for py_file in root.rglob("*.py"):
        rel = str(py_file.relative_to(_PROJECT_ROOT))
        if "__pycache__" in rel or "venv" in rel:
            continue
        if "/tests/" in rel or rel.startswith("tests/"):
            continue
        try:
            source = py_file.read_text(encoding="utf-8")
            tree = ast.parse(source, filename=rel)
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and node.name in class_names:
                hits.append((py_file, node.name))
    return hits


def _is_canonical(path: Path) -> bool:
    """Return True if the file is within the canonical core package."""
    rel = str(path.relative_to(_PROJECT_ROOT))
    return rel.startswith(_CANONICAL_PACKAGE)


def test_quote_is_single_source() -> None:
    """Quote must be defined exactly once, in brokers/common/core/."""
    hits = _find_class_definitions(_BROKERS_DIR, {"Quote"})
    non_canonical = [(f, c) for f, c in hits if not _is_canonical(f)]
    assert not non_canonical, (
        "Quote must NOT be defined outside brokers/common/core/. "
        "Found duplicates in: "
        + ", ".join(str(f.relative_to(_PROJECT_ROOT)) for f, _ in non_canonical)
    )


def test_balance_is_single_source() -> None:
    """Balance must be defined exactly once, in brokers/common/core/."""
    hits = _find_class_definitions(_BROKERS_DIR, {"Balance"})
    non_canonical = [(f, c) for f, c in hits if not _is_canonical(f)]
    assert not non_canonical, (
        "Balance must NOT be defined outside brokers/common/core/. "
        "Found duplicates in: "
        + ", ".join(str(f.relative_to(_PROJECT_ROOT)) for f, _ in non_canonical)
    )


def test_depth_types_are_single_source() -> None:
    """DepthLevel and MarketDepth must each be defined once, in common/core."""
    hits = _find_class_definitions(_BROKERS_DIR, {"DepthLevel", "MarketDepth"})
    non_canonical = [(f, c) for f, c in hits if not _is_canonical(f)]
    assert not non_canonical, (
        "DepthLevel/MarketDepth must NOT be defined outside "
        "brokers/common/core/. Found duplicates:\n"
        + "\n".join(
            f"  {c} in {f.relative_to(_PROJECT_ROOT)}" for f, c in non_canonical
        )
    )


def test_all_canonical_domain_types_are_single_source() -> None:
    """All domain types in _CANONICAL_TYPES must have exactly one definition
    and it must be in brokers/common/core/."""
    hits = _find_class_definitions(_BROKERS_DIR, _CANONICAL_TYPES)
    non_canonical = [(f, c) for f, c in hits if not _is_canonical(f)]
    assert not non_canonical, (
        "The following domain types are defined outside "
        "brokers/common/core/ and must be consolidated:\n"
        + "\n".join(
            f"  {c} in {f.relative_to(_PROJECT_ROOT)}" for f, c in non_canonical
        )
    )
