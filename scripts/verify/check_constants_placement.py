#!/usr/bin/env python3
"""Fail CI when timeout/TTL constants are defined outside the constants package."""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
CONSTANTS_ROOT = REPO_ROOT / "brokers" / "common" / "core" / "constants"
SCAN_ROOTS = (
    REPO_ROOT / "brokers",
    REPO_ROOT / "datalake",
)

PATTERN = re.compile(
    r"^\s*(_[A-Z0-9_]*(?:TTL|TIMEOUT|INTERVAL)_?[A-Z0-9_]*)\s*=\s*\d",
    re.MULTILINE,
)

ALLOWED_SUFFIXES = {".py"}
SKIP_PARTS = {"/tests/", "/test_", "__pycache__"}


def _is_allowed(path: Path) -> bool:
    try:
        path.relative_to(CONSTANTS_ROOT)
        return True
    except ValueError:
        return False


def main() -> int:
    violations: list[str] = []
    for root in SCAN_ROOTS:
        if not root.exists():
            continue
        for path in root.rglob("*.py"):
            rel = str(path.relative_to(REPO_ROOT))
            if any(part in rel for part in SKIP_PARTS):
                continue
            if _is_allowed(path):
                continue
            text = path.read_text(encoding="utf-8")
            for match in PATTERN.finditer(text):
                violations.append(f"{rel}: {match.group(1)}")
    if violations:
        print("Module-level TTL/TIMEOUT/INTERVAL constants outside constants package:")
        for line in violations[:20]:
            print(f"  - {line}")
        if len(violations) > 20:
            print(f"  ... and {len(violations) - 20} more")
        return 1
    print("Constants placement check passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
