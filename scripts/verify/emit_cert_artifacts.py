#!/usr/bin/env python3
"""Emit functional certification artifacts T0–T4 (TOS-P7-007).

Produces immutable JSON under docs/certification/artifacts/ linked by tier.
Paper-safe by default; does not require live credentials.
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
    "T1": "paper broker doctor/verify surface",
    "T2": "paper certification suite",
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
    # Also write a stable "latest" pointer per tier
    latest = OUT / f"{tier}_{broker}_latest.json"
    latest.write_text(json.dumps(body, indent=2) + "\n", encoding="utf-8")
    return path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--broker", default="paper")
    args = parser.parse_args()
    broker = args.broker

    # T0 — offline gates
    emit_tier(
        "T0",
        broker,
        {
            "import_linter": "15/15 expected",
            "architecture_tests": "tests/architecture",
            "commands": [
                "PYTHONPATH=src lint-imports --config pyproject.toml",
                "PYTHONPATH=src pytest tests/architecture -q",
            ],
        },
    )

    # T1 — doctor/verify if available
    t1: dict = {"surface": "platform_ops"}
    try:
        from brokers.platform_ops import run_doctor, run_verify

        t1["doctor"] = run_doctor(broker).to_dict()
        t1["verify"] = run_verify(broker).to_dict()
    except Exception as exc:
        t1["error"] = str(exc)
        t1["status"] = "skipped_or_failed"
    emit_tier("T1", broker, t1)

    # T2 — certify
    t2: dict = {"surface": "certify"}
    try:
        from brokers.platform_ops import run_certify

        t2["certify"] = run_certify(broker).to_dict()
    except Exception as exc:
        t2["error"] = str(exc)
        t2["status"] = "skipped_or_failed"
    emit_tier("T2", broker, t2)

    # T3 / T4 — placeholders requiring env / human sign-off
    emit_tier(
        "T3",
        broker,
        {
            "status": "manual",
            "requires": "DHAN_INTEGRATION=1 or sandbox credentials",
            "note": "Run sandbox order smoke; attach logs to this tier",
        },
    )
    emit_tier(
        "T4",
        broker,
        {
            "status": "manual",
            "requires": "live readonly / real-money approval",
            "note": "Security track deferred (ADR-023); do not claim live capital safety",
        },
    )
    print(f"wrote T0–T4 artifacts under {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
