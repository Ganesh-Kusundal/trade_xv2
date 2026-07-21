#!/usr/bin/env python3
"""CI: ban imports from the ``domain`` facade / ``domain.types`` facade in src/ (REF-9).

Canonical rule (see ``context/code-standards.md`` §3): import every domain type
from its owning submodule — ``from domain.enums import Side`` — never from the
``domain`` mega-facade (``domain/__init__.py``) or the secondary ``domain.types``
facade. Both facades are deprecated re-export shims kept only for backward
compatibility during the REF-9 migration; new code must not add new imports
through them.

A large pre-existing set of files still imports through the facades. Those are
grandfathered in ``docs/superpowers/ledgers/domain-facade-import-baseline.txt``
so CI can start blocking *new* violations today without requiring the full
~125-file migration up front. Remove a file from the ledger once it is
migrated to direct submodule imports.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
BASELINE_LEDGER = ROOT / "docs" / "superpowers" / "ledgers" / "domain-facade-import-baseline.txt"

# domain/__init__.py and domain/types.py are the facades themselves — they are
# allowed (required, even) to import from their own owning submodules.
SELF_FACADE_FILES = {
    "src/domain/__init__.py",
    "src/domain/types.py",
}

_FACADE_IMPORT = re.compile(r"^\s*from\s+domain(\.types)?\s+import\s")


def _load_baseline() -> set[str]:
    if not BASELINE_LEDGER.exists():
        return set()
    lines = BASELINE_LEDGER.read_text(encoding="utf-8").splitlines()
    return {line.strip() for line in lines if line.strip() and not line.strip().startswith("#")}


def _find_offenders() -> list[str]:
    offenders: list[str] = []
    for path in SRC.rglob("*.py"):
        rel = path.relative_to(ROOT).as_posix()
        if rel in SELF_FACADE_FILES:
            continue
        for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if _FACADE_IMPORT.match(line):
                offenders.append(f"{rel}:{i}: {line.strip()}")
    return offenders


def main() -> int:
    baseline = _load_baseline()
    offenders = _find_offenders()
    new_offenders = [o for o in offenders if o.split(":", 1)[0] not in baseline]

    if new_offenders:
        print(
            "New domain facade imports found — import from the owning submodule instead\n"
            "(e.g. `from domain.enums import Side`, not `from domain import Side`):",
            file=sys.stderr,
        )
        for item in new_offenders[:40]:
            print(f"  {item}", file=sys.stderr)
        if len(new_offenders) > 40:
            print(f"  ... and {len(new_offenders) - 40} more", file=sys.stderr)
        return 1

    grandfathered = len(offenders)
    print(
        f"OK: no new domain facade imports in src/ "
        f"({grandfathered} grandfathered import(s) remain in "
        f"{BASELINE_LEDGER.relative_to(ROOT)})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
