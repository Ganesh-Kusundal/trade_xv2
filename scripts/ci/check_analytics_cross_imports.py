#!/usr/bin/env python3
"""CI: analytics paper/replay must not cross-import (REF-14).

Both packages share logic via ``analytics.simulation`` only.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PAPER = ROOT / "src" / "analytics" / "paper"
REPLAY = ROOT / "src" / "analytics" / "replay"
FORBIDDEN_BROKER_PREFIXES = (
    "brokers.dhan",
    "brokers.upstox",
    "brokers.paper",
)


def _forbidden_imports(package: Path, forbidden_prefix: str) -> list[str]:
    offenders: list[str] = []
    for path in package.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        rel = path.relative_to(ROOT).as_posix()
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                if node.module.startswith(forbidden_prefix):
                    offenders.append(f"{rel} imports {node.module}")
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.startswith(forbidden_prefix):
                        offenders.append(f"{rel} imports {alias.name}")
    return offenders


def _analytics_broker_imports() -> list[str]:
    analytics = ROOT / "src" / "analytics"
    offenders: list[str] = []
    for prefix in FORBIDDEN_BROKER_PREFIXES:
        offenders.extend(_forbidden_imports(analytics, prefix))
    return offenders


def main() -> int:
    violations: list[str] = []
    violations.extend(_forbidden_imports(PAPER, "analytics.replay"))
    violations.extend(_forbidden_imports(REPLAY, "analytics.paper"))
    violations.extend(_analytics_broker_imports())

    if violations:
        print("Analytics cross-import / broker isolation violations (REF-14):", file=sys.stderr)
        for item in violations:
            print(f"  {item}", file=sys.stderr)
        return 1

    print("OK: analytics paper/replay isolated; no concrete broker imports")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
