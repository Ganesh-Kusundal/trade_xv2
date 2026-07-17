"""Architecture guardrail: DuckDB connections come from one place.

Target invariant (Analytics Platform roadmap, Section 4 "Single data-access
boundary"): every DuckDB connection is created through the sanctioned pool in
``datalake.core.duckdb_utils`` (``get_pool`` / ``get_read_pool`` /
``get_memory_pool`` / ``duckdb_connection``). Ad-hoc ``duckdb.connect(...)`` —
especially ``duckdb.connect(":memory:")`` — bypasses the pool and, for
``:memory:``, cannot see the catalog/views, silently returning wrong or empty
results.

This is a RATCHET, not a big-bang: the drift sites that exist today are listed
in ``EXEMPTIONS`` with the phase that removes them. The test fails if:
  * a NEW file introduces ``duckdb.connect(`` (drift prevention — the point), or
  * an ``EXEMPTIONS`` entry is stale (the file no longer calls it — tighten the
    ratchet by deleting the entry).

No behavior change: this only observes source text.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC_DIR = ROOT / "src"

# The single sanctioned owner of raw ``duckdb.connect`` (wraps it in
# ``connect_with_retry`` + the pools). Everything else must go through a pool.
SANCTIONED = {"datalake/core/duckdb_utils.py"}

# Drift sites present when the roadmap was written. Each must be routed through
# datalake.core.duckdb_utils and its entry deleted in the noted phase.
# Format: relative_path -> reason.
EXEMPTIONS: dict[str, str] = {
    "datalake/adapters/analytics_provider.py": "Provider.query() uses :memory: (broken — cannot see catalog); fix in Phase 1",
    "analytics/scanner/scanner_queries.py": "Scanner SQL uses :memory:; route through pool in Phase 1/2",
    "analytics/intraday/afternoon_expansion.py": "Intraday scan uses ad-hoc connect; route through pool in Phase 1",
    "datalake/mcp/tools.py": "MCP tool builds a per-call connection; route through pool in Phase 1",
    "datalake/normalize.py": "Ingestion normalize uses :memory:; route through pool in Phase 1",
    "datalake/ingestion/sync_options.py": "Options sync opens a raw read-only connection; route through pool in Phase 1",
    "datalake/quality/health_check.py": "Health check opens a raw read-only connection; route through pool in Phase 1",
    "datalake/quality/monitor.py": "Quality monitor's default connect_fn uses raw connect; route through pool in Phase 1",
}

EXEMPTION_METADATA: dict[str, dict[str, str]] = {
    path: {"owner": "team-analytics", "phase": "P1"} for path in EXEMPTIONS
}

_CONNECT = re.compile(r"\bduckdb\.connect\s*\(")


def _files_calling_duckdb_connect() -> set[str]:
    hits: set[str] = set()
    for py in SRC_DIR.rglob("*.py"):
        rel = py.relative_to(SRC_DIR).as_posix()
        if _CONNECT.search(py.read_text(encoding="utf-8")):
            hits.add(rel)
    return hits


def test_no_new_duckdb_connect_outside_pool() -> None:
    """Only the sanctioned pool module (or a tracked exemption) may call duckdb.connect."""
    allowed = SANCTIONED | set(EXEMPTIONS)
    offenders = sorted(f for f in _files_calling_duckdb_connect() if f not in allowed)
    assert not offenders, (
        "New direct duckdb.connect() call sites are not allowed — use "
        "datalake.core.duckdb_utils (get_pool / get_read_pool / get_memory_pool / "
        f"duckdb_connection). Offenders: {offenders}"
    )


def test_no_stale_exemptions() -> None:
    """Every exemption must still be a real call site (keeps the ratchet honest)."""
    current = _files_calling_duckdb_connect()
    stale = sorted(f for f in EXEMPTIONS if f not in current)
    assert not stale, (
        "These files no longer call duckdb.connect() — delete their EXEMPTIONS "
        f"entries to tighten the guardrail: {stale}"
    )


def test_exemptions_have_owner_and_phase() -> None:
    missing = sorted(
        p for p in EXEMPTIONS
        if not EXEMPTION_METADATA.get(p, {}).get("owner")
        or not EXEMPTION_METADATA.get(p, {}).get("phase")
    )
    assert not missing, f"Exemptions missing owner/phase metadata: {missing}"
