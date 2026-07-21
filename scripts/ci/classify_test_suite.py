#!/usr/bin/env python3
"""Classify test files for behavioral-test-suite cleanup (Phase 0 ledger).

Scans tests/**/test_*.py for implementation-coupling smells and assigns
a suggested disposition. Output: markdown table for docs/superpowers/ledgers/.
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TESTS = ROOT / "tests"

PRESERVE_EXACT = {
    "tests/integration/brokers/dhan/contract/test_broker_contract.py",
    "tests/integration/brokers/upstox/contract/test_broker_contract.py",
    "tests/integration/brokers/upstox/contract/test_upstox_contract.py",
    "tests/integration/brokers/dhan/regression/test_coverage_manifest.py",
    "tests/integration/brokers/upstox/regression/test_coverage_manifest.py",
    "tests/integration/test_risk_deny_never_hits_venue.py",
    "tests/integration/test_kill_switch_atomic_flip.py",
    "tests/integration/test_idempotent_place.py",
    "tests/integration/test_cancel_verification.py",
    "tests/component/oms/test_money_safety_invariants.py",
    "tests/component/oms/test_capital_provider_fail_closed.py",
    "tests/component/oms/test_live_path_risk_gate_and_capital.py",
    "tests/component/oms/test_order_lifecycle_end_to_end.py",
    "tests/integration/test_parity_gate.py",
    "tests/integration/test_execution_parity.py",
    "tests/integration/capability/test_capability_certification.py",
    "tests/chaos/test_recovery_certification.py",
    "tests/chaos/test_oms_lock_survives_concurrent_fills.py",
    "tests/chaos/test_reconciliation_failures.py",
    "tests/unit/brokers/common/test_acl.py",
    "tests/unit/brokers/common/test_wire_base.py",
    "tests/unit/brokers/common/test_status_mapping.py",
    "tests/unit/domain/test_parsing.py",
    "tests/e2e/test_market_data_to_order_flow.py",
}

PRESERVE_PREFIXES = (
    "tests/unit/brokers/common/contracts/",
    "tests/unit/brokers/paper/contract/",
    "tests/integration/brokers/dhan/test_live_read_surface_suite.py",
    "tests/integration/brokers/upstox/test_live_read_surface_suite.py",
    "tests/integration/quant/test_",
)

ARCH_MOVE_STATIC = {
    "tests/architecture/test_domain_isolation.py",
    "tests/architecture/test_domain_no_broker_imports.py",
    "tests/architecture/test_domain_no_tradex_imports.py",
    "tests/architecture/test_application_no_infra_imports.py",
    "tests/architecture/test_ui_no_concrete_broker_imports.py",
    "tests/architecture/test_no_tradex_in_application.py",
    "tests/architecture/test_api_no_ui_imports.py",
    "tests/architecture/test_oms_no_broker_name_branching.py",
    "tests/architecture/test_no_broker_string_branching.py",
    "tests/architecture/test_clock_purity.py",
    "tests/architecture/test_domain_no_pandas_import.py",
    "tests/architecture/test_no_scattered_dotenv.py",
    "tests/architecture/test_duckdb_single_connection_source.py",
    "tests/architecture/test_no_private_reachthrough.py",
    "tests/architecture/test_no_security_id_leak.py",
    "tests/architecture/test_broker_data_access_compliance.py",
    "tests/architecture/test_broker_kernel_guardrails.py",
    "tests/architecture/test_place_order_path_inventory.py",
    "tests/architecture/test_paper_oms_boundary.py",
    "tests/architecture/test_test_suite_uses_behavioral_names.py",
    "tests/architecture/test_workflow_paths.py",
    "tests/architecture/test_dependency_graph_sync.py",
    "tests/architecture/test_domain_single_source.py",
    "tests/architecture/test_domain_bar_types.py",
    "tests/architecture/test_domain_market_types.py",
    "tests/architecture/test_ui_broker_ops_delegation.py",
    "tests/architecture/test_deepening_enforcement.py",
    "tests/architecture/test_cross_cutting_concerns.py",
    "tests/architecture/test_production_code_fitness_rules.py",
    "tests/architecture/test_import_direction_and_layering.py",
    "tests/architecture/test_wire_boundary.py",
    "tests/architecture/test_no_interface_broker_imports.py",
    "tests/architecture/test_factory_uses_canonical_paths.py",
}

ARCH_REWRITE = {
    "tests/architecture/test_order_placement_spine.py",
    "tests/architecture/test_fail_closed_capital_paths.py",
    "tests/architecture/test_stream_oms_lock_discipline.py",
    "tests/architecture/test_execution_target_resolver.py",
    "tests/architecture/test_composition_root.py",
    "tests/architecture/test_connect_flow_compliance.py",
    "tests/architecture/test_flow_contracts.py",
    "tests/architecture/test_gateway_abc_compliance.py",
    "tests/architecture/test_gateway_surface_freeze.py",
    "tests/architecture/test_broker_routing.py",
    "tests/architecture/test_order_port_services.py",
    "tests/architecture/test_domain_ports_forbid_tradex_imports.py",
    "tests/architecture/test_domain_value_object_purity.py",
    "tests/architecture/test_single_config.py",
    "tests/architecture/test_single_idempotency.py",
    "tests/architecture/test_broker_session_state_single_source.py",
    "tests/architecture/test_no_duplicate_error_hierarchies.py",
    "tests/architecture/test_concurrency_boundary.py",
    "tests/architecture/test_streaming_gateway_port_conformance.py",
    "tests/architecture/test_module_boundaries_and_decomposition.py",
}

INTEGRATION_MOVE: set[str] = set()

COMPONENT_MOVE_UNIT: set[str] = set()

SMELL_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("ast", re.compile(r"\bast\.parse\b|\binspect\.getsource\b")),
    ("source_read", re.compile(r"read_text\s*\(|Path\s*\(\s*[\"']src/")),
    ("private", re.compile(r"(?<![\w])\.(_[a-zA-Z]\w*)")),
    ("mock", re.compile(r"\bMagicMock\b|\bunittest\.mock\b|\b@patch\b|assert_called")),
    ("signature", re.compile(r"\binspect\.signature\b|get_type_hints")),
    ("caplog", re.compile(r"\bcaplog\b")),
]


@dataclass
class Row:
    path: str
    layer: str
    smells: list[str] = field(default_factory=list)
    disposition: str = "REVIEW"
    rationale: str = ""
    replacement: str = ""


def layer_of(rel: str) -> str:
    parts = rel.split("/")
    return parts[1] if len(parts) > 1 else "unknown"


def is_preserve(rel: str) -> bool:
    if rel in PRESERVE_EXACT:
        return True
    return any(rel.startswith(p) for p in PRESERVE_PREFIXES)


def classify(rel: str, text: str, smells: list[str]) -> Row:
    row = Row(path=rel, layer=layer_of(rel), smells=smells)
    if is_preserve(rel):
        row.disposition = "KEEP"
        row.rationale = "Money-safety / contract / regression preserve list"
        return row
    if rel in ARCH_MOVE_STATIC:
        row.disposition = "MOVE_STATIC"
        row.rationale = "AST/grep/import ratchet → import-linter / CI script"
        row.replacement = "scripts/ci/ or pyproject import-linter"
        return row
    if rel in {"tests/architecture/test_factory_uses_canonical_paths.py"}:
        row.disposition = "DELETE"
        row.rationale = "Duplicate of other architecture gates"
        return row
    if rel in ARCH_REWRITE:
        row.disposition = "REWRITE"
        row.rationale = "Real contract; replace source substring with behavioral assertion"
        return row
    if rel.startswith("tests/architecture/"):
        if smells:
            row.disposition = "MOVE_STATIC" if "ast" in smells or "source_read" in smells else "REWRITE"
        else:
            row.disposition = "KEEP"
        row.rationale = row.rationale or "Architecture runtime contract"
        return row
    if rel in INTEGRATION_MOVE:
        row.disposition = "MOVE_LAYER"
        row.rationale = "Wrong pyramid layer (static or unit)"
        return row
    if rel in COMPONENT_MOVE_UNIT:
        row.disposition = "MOVE_LAYER"
        row.rationale = "Mock-heavy CLI tests belong in unit/interface/ui"
        row.replacement = "tests/unit/interface/ui/"
        return row
    if rel.startswith("tests/unit/domain/"):
        if "mock" in smells and "ast" not in smells:
            row.disposition = "REWRITE"
            row.rationale = "Use public domain API + real objects"
        elif "ast" in smells or "source_read" in smells:
            row.disposition = "MOVE_STATIC"
            row.rationale = "Source scan belongs in CI/architecture"
        else:
            row.disposition = "KEEP"
            row.rationale = "Domain behavioral / invariant test"
        return row
    if rel.startswith("tests/unit/brokers/"):
        if "ast" in smells or "source_read" in smells:
            row.disposition = "MOVE_STATIC"
            row.rationale = "Broker source hygiene → CI"
        elif "private" in smells or "mock" in smells:
            row.disposition = "REWRITE"
            row.rationale = "Assert wire→domain observables via public gateway/bus"
        else:
            row.disposition = "KEEP"
            row.rationale = "Broker contract / golden / ACL behavioral"
        return row
    if rel.startswith("tests/component/ui/") and ("mock" in smells or "source_read" in smells):
        row.disposition = "MOVE_LAYER"
        row.rationale = "UI mock tests → unit/interface/ui"
        return row
    if rel.startswith("tests/integration/") and ("ast" in smells or "source_read" in smells):
        row.disposition = "MOVE_LAYER"
        row.rationale = "No source AST in integration"
        return row
    if rel.startswith("tests/integration/") and "mock" in smells:
        row.disposition = "REWRITE"
        row.rationale = "De-mock money path; use paper/recording fakes"
        return row
    if smells:
        row.disposition = "REWRITE"
        row.rationale = f"Smells: {', '.join(smells)}"
    else:
        row.disposition = "KEEP"
        row.rationale = "Behavioral / no smell detected"
    return row


def scan() -> list[Row]:
    rows: list[Row] = []
    for path in sorted(TESTS.rglob("test_*.py")):
        rel = path.relative_to(ROOT).as_posix()
        text = path.read_text(encoding="utf-8", errors="replace")
        smells = [name for name, pat in SMELL_PATTERNS if pat.search(text)]
        rows.append(classify(rel, text, smells))
    return rows


def to_markdown(rows: list[Row]) -> str:
    from collections import Counter

    counts = Counter(r.disposition for r in rows)
    lines = [
        "# Test Disposition Ledger (Phase 0)",
        "",
        f"Generated from `{Path(__file__).relative_to(ROOT)}`. Total files: **{len(rows)}**.",
        "",
        "## Summary",
        "",
        "| Disposition | Count |",
        "|---|---:|",
    ]
    for disp in ("KEEP", "REWRITE", "MOVE_STATIC", "MOVE_LAYER", "DELETE", "REVIEW"):
        if counts[disp]:
            lines.append(f"| {disp} | {counts[disp]} |")
    lines.extend(["", "## Full ledger", "", "| Path | Layer | Disposition | Smells | Rationale |", "|---|---|---|---|---|"])
    for r in rows:
        smells = ", ".join(r.smells) if r.smells else "—"
        lines.append(f"| `{r.path}` | {r.layer} | {r.disposition} | {smells} | {r.rationale} |")
    return "\n".join(lines) + "\n"


def main() -> int:
    rows = scan()
    out_dir = ROOT / "docs" / "superpowers" / "ledgers"
    out_dir.mkdir(parents=True, exist_ok=True)
    md_path = out_dir / "test-disposition-phase0.md"
    md_path.write_text(to_markdown(rows), encoding="utf-8")
    print(f"Wrote {md_path} ({len(rows)} files)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
