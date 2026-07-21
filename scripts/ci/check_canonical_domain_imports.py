#!/usr/bin/env python3
"""CI: ban imports from the ``domain`` facade / ``domain.types`` facade in src/ (REF-9).

Canonical rule (see ``context/code-standards.md`` §3): import every domain type
from its owning submodule — ``from domain.enums import Side`` — never from the
``domain`` mega-facade (``domain/__init__.py``) or the secondary ``domain.types``
facade.

``domain/__init__.py`` only exports ``__version__``. ``domain/types.py`` is a
backward-compat re-export shim that must not be imported from new code.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"

# domain/__init__.py and domain/types.py are the facades themselves — they are
# allowed to import from their own owning submodules.
SELF_FACADE_FILES = {
    "src/domain/__init__.py",
    "src/domain/types.py",
}

_FACADE_IMPORT = re.compile(r"^\s*from\s+domain(\.types)?\s+import\s")


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
    offenders = _find_offenders()

    if offenders:
        print(
            "Domain facade imports found — import from the owning submodule instead\n"
            "(e.g. `from domain.enums import Side`, not `from domain import Side`):",
            file=sys.stderr,
        )
        for item in offenders[:40]:
            print(f"  {item}", file=sys.stderr)
        if len(offenders) > 40:
            print(f"  ... and {len(offenders) - 40} more", file=sys.stderr)
        return 1

    print("OK: no domain facade imports in src/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
