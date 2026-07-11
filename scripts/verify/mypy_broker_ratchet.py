#!/usr/bin/env python3
"""Broker mypy error-count ratchet (TOS-P7-006).

Fails if mypy error count on src/brokers rises above the stored baseline.
Does not require zero errors (full clean still incremental).
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BASELINE = ROOT / "docs" / "certification" / "baselines" / "mypy_brokers_baseline.json"


def count_errors() -> int:
    proc = subprocess.run(
        [sys.executable, "-m", "mypy", "src/brokers/", "--no-error-summary"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        env={**dict(**{k: v for k, v in __import__("os").environ.items()}), "PYTHONPATH": str(ROOT / "src")},
    )
    text = proc.stdout + proc.stderr
    m = re.search(r"Found (\d+) error", text)
    if m:
        return int(m.group(1))
    if proc.returncode == 0:
        return 0
    # Count "error:" lines as fallback
    return sum(1 for line in text.splitlines() if ": error:" in line)


def main() -> int:
    errors = count_errors()
    BASELINE.parent.mkdir(parents=True, exist_ok=True)
    if not BASELINE.exists():
        BASELINE.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "max_errors": errors,
                    "note": "Initial baseline; ratchet fails if count increases",
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        print(f"seeded baseline max_errors={errors} -> {BASELINE}")
        return 0
    data = json.loads(BASELINE.read_text(encoding="utf-8"))
    max_errors = int(data.get("max_errors", errors))
    print(f"mypy brokers errors={errors} baseline_max={max_errors}")
    if errors > max_errors:
        print(f"FAIL: broker mypy errors increased ({errors} > {max_errors})")
        return 1
    # Optionally tighten baseline when improved
    if errors < max_errors:
        data["max_errors"] = errors
        data["last_improved_to"] = errors
        BASELINE.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        print(f"tightened baseline to {errors}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
