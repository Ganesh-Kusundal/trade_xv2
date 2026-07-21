#!/usr/bin/env python3
"""Static guards against logging secrets in production code (SEC-05)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"


def main() -> int:
    violations: list[str] = []

    auth_path = SRC / "interface" / "api" / "auth.py"
    if auth_path.is_file():
        if "Generated temporary key: %s" in auth_path.read_text(encoding="utf-8"):
            violations.append(f"{auth_path.relative_to(ROOT)}: API key logged via format string")

    brokers = SRC / "brokers"
    if brokers.is_dir():
        for path in brokers.rglob("*.py"):
            if "test" in path.parts or path.name == "logging_config.py":
                continue
            for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                stripped = line.strip()
                if stripped.startswith("#"):
                    continue
                if (
                    "logger." in line
                    and ("token=%s" in line or 'token="{}"' in line)
                    and "REDACTED" not in line
                ):
                    violations.append(f"{path.relative_to(ROOT)}:{lineno}")

    if violations:
        print("Secret logging violations:\n" + "\n".join(violations[:50]), file=sys.stderr)
        return 1
    print("OK: no secret logging patterns in production code")
    return 0


if __name__ == "__main__":
    sys.exit(main())
