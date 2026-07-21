#!/usr/bin/env python3
"""GOV-2: ADR-011 LOC limit (replaces tests/architecture/test_file_size_limit.py)."""

from __future__ import annotations

import sys
from pathlib import Path

MAX_LOC = 670
SRC = Path(__file__).resolve().parents[2] / "src"


def main() -> int:
    violations: list[str] = []
    for py in SRC.rglob("*.py"):
        loc = len(py.read_text(encoding="utf-8").splitlines())
        if loc > MAX_LOC:
            violations.append(f"{py.relative_to(SRC.parent)}: {loc} LOC (max {MAX_LOC})")
    if violations:
        print("LOC violations:\n" + "\n".join(violations[:20]), file=sys.stderr)
        if len(violations) > 20:
            print(f"... and {len(violations) - 20} more", file=sys.stderr)
        return 1
    print(f"OK: all files <= {MAX_LOC} LOC")
    return 0


if __name__ == "__main__":
    sys.exit(main())
