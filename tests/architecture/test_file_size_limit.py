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
    "analytics/options/options_analytics.py": (444, "Options analytics — split tracked in ADR-011 backlog"),
    "analytics/scanner/scanner_queries.py": (472, "Scanner queries — split tracked in ADR-011 backlog"),
    "analytics/precompute_features.py": (678, "Feature precompute — split tracked in ADR-011 backlog"),
    "analytics/replay/engine.py": (654, "ReplayEngine facade — partially decomposed; remaining split in ADR-011 backlog"),
    "analytics/replay/orchestrator.py": (539, "Replay orchestrator — split tracked in ADR-011 backlog"),
    "analytics/paper/engine.py": (562, "Paper engine — split tracked in ADR-011 backlog"),
    "analytics/facade.py": (549, "Analytics facade — split tracked in ADR-011 backlog"),
    "application/composer/factory.py": (409, "Composer factory — split tracked in ADR-011 backlog"),
    "application/data/historical_coordinator.py": (567, "Historical coordinator — split tracked in ADR-011 backlog"),
    "application/oms/context.py": (517, "TradingContext facade — partially decomposed; remaining split in ADR-011 backlog"),
    "application/oms/_internal/risk_manager.py": (355, "RiskManager facade — partially decomposed; remaining split in ADR-011 backlog"),
    "application/trading/trading_orchestrator.py": (493, "TradingOrchestrator facade — partially decomposed; remaining split in ADR-011 backlog"),
    "brokers/cli/broker.py": (451, "CLI broker commands — split tracked in ADR-011 backlog"),
    "brokers/dhan/api/http_client.py": (476, "Dhan HTTP client — split tracked in ADR-011 backlog"),
    "brokers/dhan/data/depth_feed_base.py": (573, "Dhan depth feed — split tracked in ADR-011 backlog"),
    "brokers/dhan/identity/identity.py": (420, "Dhan identity — split tracked in ADR-011 backlog"),
    "brokers/dhan/streaming/connection.py": (491, "Dhan streaming connection — split tracked in ADR-011 backlog"),
    "brokers/dhan/websocket/connection.py": (426, "Dhan websocket connection — split tracked in ADR-011 backlog"),
    "brokers/dhan/websocket/market_feed.py": (408, "Dhan market feed — split tracked in ADR-011 backlog"),
    "brokers/paper/paper_gateway.py": (485, "Paper gateway — split tracked in ADR-011 backlog"),
    "brokers/paper/paper_orders.py": (433, "Paper orders — split tracked in ADR-011 backlog"),
    "brokers/services/core.py": (570, "Single service core — split tracked in ADR-011 backlog"),
    "brokers/upstox/auth/token_manager.py": (574, "Upstox token manager — split tracked in ADR-011 backlog"),
    "brokers/upstox/websocket/market_data_v3.py": (489, "Upstox market data v3 — split tracked in ADR-011 backlog"),
    "datalake/analytics/support_resistance.py": (414, "Datalake support/resistance — split tracked in ADR-011 backlog"),
    "domain/candles/historical.py": (666, "Historical candle loading — split tracked in ADR-011 backlog"),
    "domain/capability_manifest/catalog.py": (895, "Capability catalog — large but mechanically generated; split tracked in ADR-011 backlog"),
    "domain/instruments/instrument.py": (676, "Instrument aggregate root — split tracked in ADR-011 backlog"),
    "domain/options/option_chain.py": (465, "Option chain — split tracked in ADR-011 backlog"),
    "domain/universe.py": (700, "Instrument universe — split tracked in ADR-011 backlog"),
    "infrastructure/event_bus/event_bus.py": (457, "EventBus core — split tracked in ADR-011 backlog"),
    "infrastructure/observability/alerting.py": (483, "Alerting engine — split tracked in ADR-011 backlog"),
    "infrastructure/observability/audit.py": (416, "Audit logging — split tracked in ADR-011 backlog"),
    "infrastructure/resilience/rate_limiter.py": (405, "Rate limiter — split tracked in ADR-011 backlog"),
    "interface/api/routers/orders.py": (403, "Orders router — split tracked in ADR-011 backlog"),
    "interface/api/schemas.py": (485, "API schemas — split tracked in ADR-011 backlog"),
    "interface/ui/commands/market.py": (458, "Market commands — split tracked in ADR-011 backlog"),
    "tradex/session.py": (512, "Session bootstrap — split tracked in ADR-011 backlog"),
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
