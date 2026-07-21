#!/usr/bin/env python3
"""Emit functional certification artifacts T0 / T3 / T4 (TOS-P7-007).

T1/T2 (doctor/verify/certify via brokers.platform_ops) were removed when
``src/brokers`` was purified — those surfaces no longer exist. Artifacts for
T0 (offline gates) and manual T3/T4 remain.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "docs" / "certification" / "artifacts"

TIERS = {
    "T0": "unit/architecture gates (offline)",
    "T3": "sandbox order smoke (optional env)",
    "T4": "live readonly / real-money (manual evidence)",
}


def _sha(payload: dict) -> str:
    raw = json.dumps(payload, sort_keys=True).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def emit_tier(tier: str, broker: str, evidence: dict) -> Path:
    body = {
        "schema_version": 1,
        "tier": tier,
        "tier_description": TIERS[tier],
        "broker": broker,
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "evidence": evidence,
    }
    body["content_sha256"] = _sha(body)
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / f"{tier}_{broker}_{body['recorded_at'][:10]}.json"
    path.write_text(json.dumps(body, indent=2) + "\n", encoding="utf-8")
    latest = OUT / f"{tier}_{broker}_latest.json"
    latest.write_text(json.dumps(body, indent=2) + "\n", encoding="utf-8")
    return path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--broker", default="paper")
    args = parser.parse_args()
    broker = args.broker

    emit_tier(
        "T0",
        broker,
        {
            "import_linter": "expected",
            "architecture_tests": "tests/architecture",
            "commands": [
                "PYTHONPATH=src lint-imports --config pyproject.toml",
                "PYTHONPATH=src pytest tests/architecture -q",
            ],
        },
    )

    emit_tier(
        "T3",
        broker,
        {
            "status": "manual",
            "note": "Sandbox order smoke — operator evidence only",
        },
    )
    emit_tier(
        "T4",
        broker,
        {
            "status": "manual",
            "note": "Live readonly / real-money — operator evidence only",
        },
    )
    print(f"Wrote artifacts under {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
