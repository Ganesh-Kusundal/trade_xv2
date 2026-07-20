#!/usr/bin/env python3
"""GOV-2: Enforce ADR-011 650 LOC limit."""

import sys
from pathlib import Path

MAX_LOC = 650
SRC = Path("src")


def check():
    violations = []
    for py in SRC.rglob("*.py"):
        loc = len(py.read_text().splitlines())
        if loc > MAX_LOC:
            violations.append(f"{py}: {loc} LOC (max {MAX_LOC})")
    if violations:
        print("LOC violations found:")
        for v in violations:
            print(f"  {v}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(check())
