#!/usr/bin/env python3
"""Generate capability coverage report from domain.capability_manifest.

Usage:
    python scripts/capability_report.py
    python scripts/capability_report.py --surface cli
    python scripts/capability_report.py --markdown docs/audits/CAPABILITY_COVERAGE_MATRIX.md
    python scripts/capability_report.py --fail-on P0
"""

from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from domain.capability_manifest import (
    CAPABILITY_SURFACES,
    CapabilitySurface,
    Severity,
    classify_exposure,
)

SEVERITY_ORDER: dict[str, int] = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}


def _gap_severity(surface: CapabilitySurface) -> Severity | None:
    status = classify_exposure(surface)
    if status in ("exposed", "broker_only"):
        return None
    if surface.broker.upstox_known_gap:
        return "P0"
    return surface.severity_if_gap


def _format_surface_row(surface: CapabilitySurface) -> str:
    status = classify_exposure(surface)
    sev = _gap_severity(surface)
    sev_tag = f" [{sev}]" if sev else ""
    cap = surface.capability.value if surface.capability else "—"
    cli_cmds = ", ".join(c.command for c in surface.cli) or "—"
    rest_routes = ", ".join(f"{r.method} {r.path}" for r in surface.rest) or "—"
    dhan = surface.broker.dhan or "—"
    upstox = surface.broker.upstox or "—"
    gw = surface.gateway_method or "—"
    return (
        f"| `{surface.id}` | {cap} | {gw} | {dhan} | {upstox} | "
        f"{cli_cmds} | {rest_routes} | {status}{sev_tag} |"
    )


def generate_markdown() -> str:
    lines: list[str] = [
        "# Capability Coverage Matrix",
        "",
        "Auto-generated from `domain/capability_manifest.py`.",
        "Do not edit manually — run `python scripts/capability_report.py --markdown`.",
        "",
        "## Summary",
        "",
    ]

    by_status: dict[str, list[CapabilitySurface]] = defaultdict(list)
    gaps_by_severity: dict[str, list[CapabilitySurface]] = defaultdict(list)

    for surface in CAPABILITY_SURFACES:
        status = classify_exposure(surface)
        by_status[status].append(surface)
        sev = _gap_severity(surface)
        if sev:
            gaps_by_severity[sev].append(surface)

    lines.append(f"- Total surfaces: **{len(CAPABILITY_SURFACES)}**")
    for status in ("exposed", "partial", "mismatch", "gap", "broker_only"):
        lines.append(f"- {status}: **{len(by_status[status])}**")
    lines.append("")

    for sev in ("P0", "P1", "P2", "P3"):
        items = gaps_by_severity.get(sev, [])
        if items:
            lines.append(f"### {sev} gaps ({len(items)})")
            lines.append("")
            for s in items:
                note = s.broker.upstox_known_gap or s.notes or s.broker_only_reason or ""
                lines.append(f"- `{s.id}` — {note}")
            lines.append("")

    lines.extend(
        [
            "## Full Matrix",
            "",
            "| ID | Capability | Gateway | Dhan | Upstox | CLI | REST | Status |",
            "|----|------------|---------|------|--------|-----|------|--------|",
        ]
    )
    for surface in CAPABILITY_SURFACES:
        lines.append(_format_surface_row(surface))
    lines.append("")
    return "\n".join(lines)


def print_console_report(surface_filter: str | None = None) -> int:
    gaps: list[tuple[Severity, CapabilitySurface]] = []
    for surface in CAPABILITY_SURFACES:
        sev = _gap_severity(surface)
        if sev is None:
            continue
        if surface_filter == "cli" and surface.cli:
            continue
        if surface_filter == "rest" and surface.rest:
            continue
        gaps.append((sev, surface))

    gaps.sort(key=lambda x: SEVERITY_ORDER.get(x[0], 99))
    print(f"Capability Coverage Report — {len(CAPABILITY_SURFACES)} surfaces")
    print("=" * 60)
    if not gaps:
        print("No gaps detected.")
        return 0
    for sev, surface in gaps:
        status = classify_exposure(surface)
        print(f"[{sev}] {surface.id} — {status}")
        if surface.broker.upstox_known_gap:
            print(f"       {surface.broker.upstox_known_gap}")
        elif surface.notes:
            print(f"       {surface.notes}")
    return len(gaps)


def main() -> int:
    parser = argparse.ArgumentParser(description="Capability coverage report")
    parser.add_argument("--markdown", type=str, help="Write markdown report to path")
    parser.add_argument("--surface", choices=["cli", "rest"], help="Filter gaps by surface")
    parser.add_argument(
        "--fail-on", choices=["P0", "P1", "P2", "P3"], help="Exit 1 if gaps at severity"
    )
    args = parser.parse_args()

    if args.markdown:
        out = Path(args.markdown)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(generate_markdown(), encoding="utf-8")
        print(f"Wrote {out}")

    gap_count = print_console_report(args.surface)

    if args.fail_on:
        threshold = SEVERITY_ORDER[args.fail_on]
        blocking = [
            s
            for s in CAPABILITY_SURFACES
            if (sev := _gap_severity(s)) is not None and SEVERITY_ORDER[sev] <= threshold
        ]
        if blocking:
            print(f"\nFAIL: {len(blocking)} gap(s) at or above {args.fail_on}")
            return 1
    return 0  # non-blocking by default


if __name__ == "__main__":
    raise SystemExit(main())
