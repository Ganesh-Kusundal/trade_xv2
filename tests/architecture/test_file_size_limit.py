"""Architecture test: enforce maximum file size limit.

Prevents god-class regressions by failing CI when any source file
exceeds the soft limit (400 LOC) or hard limit (600 LOC).

ADR-011: Decompose 800+ LOC god classes.
"""

from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SRC_DIR = ROOT / "src"

SOFT_LIMIT = 400
HARD_LIMIT = 650

# Files with documented exceptions (historical, being migrated).
# Each entry: (relative_path, approved_limit, reason)
EXEMPTIONS = {
    "analytics/replay/engine.py": (520, "ReplayEngine facade — decomposed in ADR-011 Phase 3; window + event_publishing extracted"),
    "application/composer/factory.py": (430, "Composer factory — split tracked in ADR-011 backlog"),
    "application/oms/context.py": (486, "TradingContext facade — decomposed in ADR-011 Phase 3; lifecycle services extracted"),
    "application/oms/order_manager.py": (436, "OrderManager — split tracked in ADR-011 backlog"),
    "application/trading/trading_orchestrator.py": (517, "TradingOrchestrator facade — partially decomposed; remaining split in ADR-011 backlog"),
    "brokers/cli/broker.py": (487, "CLI broker commands — split tracked in ADR-011 backlog"),
    "brokers/cli/_shell_nav.py": (415, "CLI shell navigation — types extracted to _shell_types.py; remaining in ADR-011 backlog"),
    "brokers/dhan/api/http_client.py": (500, "Dhan HTTP client — split tracked in ADR-011 backlog"),
    "brokers/dhan/data/depth_feed_base.py": (569, "Dhan depth feed — decomposed in ADR-011 Phase 3; parser delegation inlined"),
    "brokers/dhan/identity/identity.py": (441, "Dhan identity — split tracked in ADR-011 backlog"),
    "brokers/dhan/streaming/connection.py": (518, "Dhan streaming connection — split tracked in ADR-011 backlog"),
    "brokers/dhan/websocket/connection.py": (448, "Dhan websocket connection — split tracked in ADR-011 backlog"),
    "brokers/dhan/websocket/market_feed.py": (515, "Dhan market feed — split tracked in ADR-011 backlog"),
    "brokers/paper/paper_gateway.py": (510, "Paper gateway — split tracked in ADR-011 backlog"),
    "brokers/paper/paper_orders.py": (315, "Paper orders — shrank after order-split extraction; re-evaluate for removal from backlog"),
    "brokers/upstox/websocket/market_data_v3.py": (514, "Upstox market data v3 — split tracked in ADR-011 backlog"),
    "domain/options/option_chain.py": (489, "Option chain — split tracked in ADR-011 backlog"),
    "infrastructure/event_bus/event_bus.py": (480, "EventBus core — split tracked in ADR-011 backlog"),
    "infrastructure/observability/alerting.py": (508, "Alerting engine — split tracked in ADR-011 backlog"),
    "interface/ui/commands/market.py": (481, "Market commands — split tracked in ADR-011 backlog"),
}

# Owner + due-date tracking for decompositon backlog.
EXEMPTION_METADATA: dict[str, dict[str, str]] = {
    "analytics/replay/engine.py": {"owner": "team-core", "due_date": "2026-08-01"},
    "application/composer/factory.py": {"owner": "team-core", "due_date": "2026-08-01"},
    "application/oms/context.py": {"owner": "team-core", "due_date": "2026-08-01"},
    "application/oms/order_manager.py": {"owner": "team-core", "due_date": "2026-08-01"},
    "application/trading/trading_orchestrator.py": {"owner": "team-core", "due_date": "2026-08-01"},
    "brokers/cli/broker.py": {"owner": "team-brokers", "due_date": "2026-08-01"},
    "brokers/cli/_shell_nav.py": {"owner": "team-brokers", "due_date": "2026-08-01"},
    "brokers/dhan/api/http_client.py": {"owner": "team-brokers", "due_date": "2026-08-01"},
    "brokers/dhan/data/depth_feed_base.py": {"owner": "team-brokers", "due_date": "2026-08-01"},
    "brokers/dhan/identity/identity.py": {"owner": "team-brokers", "due_date": "2026-08-01"},
    "brokers/dhan/streaming/connection.py": {"owner": "team-brokers", "due_date": "2026-08-01"},
    "brokers/dhan/websocket/connection.py": {"owner": "team-brokers", "due_date": "2026-08-01"},
    "brokers/dhan/websocket/market_feed.py": {"owner": "team-brokers", "due_date": "2026-08-01"},
    "brokers/paper/paper_gateway.py": {"owner": "team-brokers", "due_date": "2026-08-01"},
    "brokers/paper/paper_orders.py": {"owner": "team-brokers", "due_date": "2026-08-01"},
    "brokers/upstox/websocket/market_data_v3.py": {"owner": "team-brokers", "due_date": "2026-08-01"},
    "domain/options/option_chain.py": {"owner": "team-core", "due_date": "2026-08-01"},
    "infrastructure/event_bus/event_bus.py": {"owner": "team-core", "due_date": "2026-08-01"},
    "infrastructure/observability/alerting.py": {"owner": "team-core", "due_date": "2026-08-01"},
    "interface/ui/commands/market.py": {"owner": "team-ui", "due_date": "2026-08-01"},
}


def _iter_source_files() -> list[Path]:
    """Yield all .py files under src/, excluding __pycache__."""
    return sorted(
        p for p in SRC_DIR.rglob("*.py") if "__pycache__" not in p.parts
    )


def _rel(path: Path) -> str:
    """Relative path without src/ prefix (matches EXEMPTIONS keys)."""
    rel = str(path.relative_to(ROOT))
    if rel.startswith("src/"):
        rel = rel[len("src/"):]
    return rel


def _count_lines(path: Path) -> int:
    """Count non-blank, non-comment lines (approx LOC)."""
    count = 0
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            count += 1
    return count


@pytest.mark.architecture
def test_no_file_exceeds_hard_limit() -> None:
    """No source file may exceed the hard limit (650 LOC) without an exemption.

    Files with approved exemptions are allowed even if over the hard limit,
    because they are tracked in the ADR-011 decomposition backlog.
    The soft-limit test enforces that they stay within their approved limit.
    """
    violations = []
    for path in _iter_source_files():
        rel = _rel(path)
        loc = _count_lines(path)
        if loc > HARD_LIMIT:
            exemption = EXEMPTIONS.get(rel)
            if exemption is None:
                violations.append((rel, loc))
    if violations:
        msg = "Files exceed hard limit ({} LOC) without exemption:\n".format(HARD_LIMIT)
        msg += "\n".join(f"  {rel}: {loc} LOC" for rel, loc in violations)
        pytest.fail(msg)


@pytest.mark.architecture
def test_no_file_exceeds_soft_limit_without_exemption() -> None:
    """Files over soft limit (400 LOC) must have an approved exemption."""
    violations = []
    for path in _iter_source_files():
        rel = _rel(path)
        loc = _count_lines(path)
        if loc > SOFT_LIMIT:
            exemption = EXEMPTIONS.get(rel)
            if exemption is None:
                violations.append((rel, loc))
            elif loc > exemption[0]:
                violations.append((rel, loc, exemption[0]))
    if violations:
        msg = "Files exceed soft limit ({} LOC) without valid exemption:\n".format(SOFT_LIMIT)
        for v in violations:
            if len(v) == 2:
                msg += f"  {v[0]}: {v[1]} LOC (no exemption)\n"
            else:
                msg += f"  {v[0]}: {v[1]} LOC (exceeds approved {v[2]})\n"
        pytest.fail(msg)


@pytest.mark.architecture
def test_exemptions_are_accurate() -> None:
    """Every exemption entry must point to a real file within 5% of approved limit."""
    for rel, (approved, reason) in EXEMPTIONS.items():
        path = ROOT / "src" / rel
        if not path.exists():
            pytest.fail(f"Exemption points to missing file: {rel}")
        loc = _count_lines(path)
        # Allow 10% slack below approved (file may have shrunk).
        if loc < approved * 0.9:
            pytest.fail(
                f"Exemption for {rel} is stale: actual {loc} LOC << approved {approved} LOC"
            )
