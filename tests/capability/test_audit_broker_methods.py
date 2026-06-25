"""Snapshot test for broker method audit script."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_audit_broker_methods_json_structure() -> None:
    result = subprocess.run(
        [sys.executable, str(PROJECT_ROOT / "scripts" / "audit_broker_methods.py"), "--json"],
        capture_output=True,
        text=True,
        cwd=PROJECT_ROOT,
        check=True,
    )
    data = json.loads(result.stdout)
    assert "dhan" in data
    assert "upstox" in data
    assert data["dhan"]["total_methods"] > 20
    assert data["upstox"]["total_methods"] > 20
    assert "domains" in data["dhan"]
    dhan_domains = data["dhan"]["domains"]
    all_files = [f["file"] for domain in dhan_domains.values() for f in domain.get("files", [])]
    assert any("orders" in f for f in all_files)
