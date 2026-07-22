#!/usr/bin/env python3
"""Write ADR-0013 Gate 3 weekly chaos-green artifact after a green pytest run."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path


def _chaos_test_count() -> int:
    root = Path(__file__).resolve().parents[2]
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "tests/chaos/",
            "-m",
            "chaos",
            "--collect-only",
            "-q",
        ],
        capture_output=True,
        text=True,
        check=False,
        cwd=root,
        env={**os.environ, "PYTHONPATH": os.environ.get("PYTHONPATH", "src")},
    )
    if proc.returncode not in (0, 5):
        return 0
    for line in proc.stdout.splitlines():
        line = line.strip()
        if " tests collected" in line or line.endswith(" test collected"):
            token = line.split()[0]
            if token.isdigit():
                return int(token)
    return 0


def main() -> int:
    out = Path(os.environ.get("CHAOS_ARTIFACT_PATH", "artifacts/adr-0013-chaos-green.json"))
    out.parent.mkdir(parents=True, exist_ok=True)

    now = datetime.now(UTC)
    iso_year, iso_week, _ = now.isocalendar()
    week_id = f"{iso_year}-W{iso_week:02d}"

    payload = {
        "gate": "ADR-0013-3",
        "status": "green",
        "iso_week": week_id,
        "timestamp_utc": now.isoformat(),
        "tests_collected": _chaos_test_count(),
        "required_consecutive_weeks": 4,
        "workflow": os.environ.get("GITHUB_WORKFLOW", "local"),
        "run_id": os.environ.get("GITHUB_RUN_ID", ""),
        "sha": os.environ.get("GITHUB_SHA", ""),
        "ref": os.environ.get("GITHUB_REF", ""),
    }

    out.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"chaos-green artifact: {out} ({week_id})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
