#!/usr/bin/env python3
"""CI: flag hardcoded ``"NSE"`` as a function-parameter default in src/ (REF-3).

Use ``DEFAULT_EXCHANGE`` from ``domain.constants`` or require explicit exchange.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"

# Allowed: constants module definitions, segment codes, comparisons, wire mappings
SKIP_PREFIXES = (
    "src/domain/constants/",
    "src/domain/market_enums.py",
    "src/config/",
)
PARAM_DEFAULT = re.compile(r"=\s*[\"']NSE[\"']")


def main() -> int:
    offenders: list[str] = []
    for path in SRC.rglob("*.py"):
        rel = path.relative_to(ROOT).as_posix()
        if any(rel.startswith(p) for p in SKIP_PREFIXES):
            continue
        for i, line in enumerate(path.read_text().splitlines(), 1):
            if "DEFAULT_EXCHANGE" in line:
                continue
            if PARAM_DEFAULT.search(line) and "def " in line or ":" in line:
                # parameter default pattern
                if PARAM_DEFAULT.search(line):
                    offenders.append(f"{rel}:{i}: {line.strip()}")
    if offenders:
        print("Hardcoded NSE parameter defaults found (use DEFAULT_EXCHANGE):", file=sys.stderr)
        for item in offenders[:40]:
            print(f"  {item}", file=sys.stderr)
        if len(offenders) > 40:
            print(f"  ... and {len(offenders) - 40} more", file=sys.stderr)
        return 1
    print("OK: no hardcoded NSE parameter defaults outside allowlist")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
