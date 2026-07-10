"""Guardrail: segment/exchange wire maps must import domain.constants.exchanges."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2] / "src" / "brokers"

# Modules that must import domain.constants.exchanges (REF-3b / REF-11).
_REQUIRED = (
    "dhan/segments.py",
    "dhan/extensions/depth20.py",
    "dhan/extensions/depth200.py",
    "upstox/instruments/segment_mapper.py",
    "upstox/extensions/depth.py",
    "dhan/wire.py",
    "upstox/wire.py",
)


def test_wire_maps_import_domain_exchanges():
    missing = []
    for rel in _REQUIRED:
        path = ROOT / rel
        text = path.read_text(encoding="utf-8")
        if "domain.constants.exchanges" not in text:
            missing.append(rel)
    assert not missing, f"missing domain.constants.exchanges import: {missing}"


def test_no_phantom_brokers_common_core_in_broker_packages():
    hits = []
    for path in ROOT.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        if "brokers.common.core." in text or "brokers.common.lifecycle." in text:
            hits.append(str(path.relative_to(ROOT)))
    assert not hits, f"phantom brokers.common.* refs: {hits}"
