#!/usr/bin/env python3
"""Migrate deprecated shim imports to canonical domain imports.

Reads the deprecation shim files to discover the canonical source,
then rewrites all non-shim .py files to import from domain/ directly
instead of brokers/common/core/.

Usage:
    python scripts/migrate_shim_imports.py          # dry-run (report only)
    python scripts/migrate_shim_imports.py --apply  # apply changes
    python scripts/migrate_shim_imports.py --verify # verify no shims remain
"""
from __future__ import annotations

import argparse
import ast
import re
import sys
from pathlib import Path
from typing import NamedTuple


ROOT = Path(__file__).resolve().parent.parent

# Maps shim module → canonical module.  Derived from the shim files
# themselves (each shim does ``from domain.X import *``).
SHIM_TO_CANONICAL: dict[str, str] = {
    "brokers.common.core.domain": "domain",
    "brokers.common.core.types": "domain.types",
    "brokers.common.core.field_mapping": "domain.field_mapping",
    "brokers.common.core.requests": "domain.requests",
    "brokers.common.core.result": "domain.result",
    "brokers.common.core.reconciliation": "domain.reconciliation",
    "brokers.common.core.exchange_segments": "domain.exchange_segments",
    "brokers.common.core.parsing": "domain.parsing",
}

# Files that ARE the shims or barrel files — never rewrite these.
SHIM_FILES: set[str] = {
    str(ROOT / p) for p in [
        "brokers/common/core/models.py",
        "brokers/common/core/domain.py",
        "brokers/common/core/types.py",
        "brokers/common/core/field_mapping.py",
        "brokers/common/core/requests.py",
        "brokers/common/core/result.py",
        "brokers/common/core/reconciliation.py",
        "brokers/common/core/exchange_segments.py",
        "brokers/common/core/parsing.py",
        "brokers/common/core/__init__.py",
        "brokers/common/__init__.py",
        "brokers/__init__.py",
    ]
}


class Replacement(NamedTuple):
    file: str
    line: int
    old: str
    new: str


def _iter_py_files() -> list[Path]:
    """Return all .py files under ROOT, excluding shims and caches."""
    py_files: list[Path] = []
    for py in ROOT.rglob("*.py"):
        if "__pycache__" in str(py):
            continue
        if ".mypy_cache" in str(py):
            continue
        if str(py) in SHIM_FILES:
            continue
        py_files.append(py)
    return sorted(py_files)


def _find_replacements(filepath: Path) -> list[Replacement]:
    """Find all shim imports in a file and produce canonical replacements."""
    try:
        source = filepath.read_text(encoding="utf-8")
    except Exception:
        return []

    replacements: list[Replacement] = []

    # Strategy: match ``from brokers.common.core.<sub> import ...``
    # and replace the module part only, preserving the imported names.
    pattern = re.compile(
        r"(?P<indent>^[ \t]*from )"
        r"brokers\.common\.core\.(?P<sub>domain|types|field_mapping|requests|result|reconciliation|exchange_segments|parsing)"
        r"(?P<rest> import .*)$",
        re.MULTILINE,
    )

    for match in pattern.finditer(source):
        sub = match.group("sub")
        canonical = SHIM_TO_CANONICAL.get(f"brokers.common.core.{sub}")
        if canonical is None:
            continue

        old = match.group(0)
        new = f"{match.group('indent')}{canonical}{match.group('rest')}"
        line_no = source[:match.start()].count("\n") + 1
        replacements.append(Replacement(str(filepath.relative_to(ROOT)), line_no, old.rstrip(), new.rstrip()))

    return replacements


def dry_run() -> int:
    """Report all shim imports without changing files."""
    count = 0
    for filepath in _iter_py_files():
        reps = _find_replacements(filepath)
        for r in reps:
            print(f"{r.file}:{r.line}:  {r.old}  →  {r.new}")
            count += 1
    print(f"\nTotal: {count} shim import(s) found across {len(_iter_py_files())} files scanned")
    return count


def apply() -> int:
    """Rewrite all shim imports to canonical imports."""
    changed_files: set[str] = set()
    total = 0

    for filepath in _iter_py_files():
        reps = _find_replacements(filepath)
        if not reps:
            continue

        source = filepath.read_text(encoding="utf-8")
        for r in reps:
            # Use the full original line (including indent) for replacement
            source = source.replace(r.old, r.new, 1)
            total += 1

        filepath.write_text(source, encoding="utf-8")
        changed_files.add(str(filepath.relative_to(ROOT)))

    print(f"Rewrote {total} imports in {len(changed_files)} files.")
    return total


def verify() -> int:
    """Exit 0 if no shim imports remain, 1 otherwise."""
    count = 0
    for filepath in _iter_py_files():
        reps = _find_replacements(filepath)
        for r in reps:
            print(f"REMAINING: {r.file}:{r.line}: {r.old}")
            count += 1
    if count:
        print(f"\nFAIL: {count} shim imports still present.")
        return 1
    print("OK: No shim imports remain.")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Migrate shim imports to canonical domain imports.")
    parser.add_argument("--apply", action="store_true", help="Apply replacements (default: dry-run)")
    parser.add_argument("--verify", action="store_true", help="Verify no shim imports remain (exit 1 if any)")
    args = parser.parse_args()

    if args.verify:
        sys.exit(verify())
    elif args.apply:
        apply()
    else:
        dry_run()


if __name__ == "__main__":
    main()
