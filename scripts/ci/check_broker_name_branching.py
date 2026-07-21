#!/usr/bin/env python3
"""OMS/cert/rate-limiter must not branch on live broker name strings."""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"

LIVE_BROKER_NAMES = {
    "dhan", "upstox", "zerodha", "angel", "kite", "fyers", "aliceblue",
    "icici", "kotak", "paytm", "5paisa", "edelweiss", "iifl", "mastertrust",
    "motilal", "sasonline", "tradejini", "samco", "trustline", "wisdom",
    "compositedge", "finvasia", "zebu",
}

SCAN_DIRS = (
    SRC / "application" / "oms",
    SRC / "infrastructure" / "resilience",
)

# String compare patterns: == "dhan", in ("dhan",), broker_id == 'upstox'
_COMPARE = re.compile(
    r"""==\s*['"]({names})['"]|in\s*\([^)]*['"]({names})['"]""".format(
        names="|".join(re.escape(n) for n in LIVE_BROKER_NAMES)
    ),
    re.IGNORECASE,
)


def main() -> int:
    violations: list[str] = []
    for base in SCAN_DIRS:
        if not base.is_dir():
            continue
        for path in base.rglob("*.py"):
            text = path.read_text(encoding="utf-8")
            for i, line in enumerate(text.splitlines(), 1):
                if line.strip().startswith("#"):
                    continue
                if _COMPARE.search(line):
                    violations.append(f"{path.relative_to(ROOT)}:{i}: {line.strip()}")
    if violations:
        print("Broker name branching violations:\n" + "\n".join(violations[:30]), file=sys.stderr)
        return 1
    print("OK: no live broker name branching in OMS/resilience")
    return 0


if __name__ == "__main__":
    sys.exit(main())
