"""Architecture compliance — UI commands delegate to brokers.services via broker_ops."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
COMMANDS_ROOT = PROJECT_ROOT / "src" / "interface" / "ui" / "commands"

# Files that may still open sessions, call wire gateways, or sit above broker_ops.
_BROKER_SESSION_ALLOWLIST: set[Path] = {
    COMMANDS_ROOT / "oms.py",
    COMMANDS_ROOT / "order_placement.py",
    COMMANDS_ROOT / "order_composition.py",
    COMMANDS_ROOT / "extended_orders.py",
    COMMANDS_ROOT / "websocket.py",
    COMMANDS_ROOT / "auth.py",
    COMMANDS_ROOT / "load_test.py",
    COMMANDS_ROOT / "news.py",
    COMMANDS_ROOT / "market.py",  # stream/option-chain wire UX
    COMMANDS_ROOT / "validate.py",  # futures/options wire extension
    COMMANDS_ROOT / "asset.py",
    COMMANDS_ROOT / "instrument.py",  # catalog via active_broker gateway
    COMMANDS_ROOT / "instruments.py",
    COMMANDS_ROOT / "search.py",
    COMMANDS_ROOT / "livefeed.py",  # FeedProbe domain path
    COMMANDS_ROOT / "analytics_stock.py",
    COMMANDS_ROOT / "analytics.py",
}

# Migrated command modules must import broker_ops or brokers.services.
_DELEGATION_REQUIRED: set[Path] = {
    COMMANDS_ROOT / "account.py",
    COMMANDS_ROOT / "portfolio.py",
    COMMANDS_ROOT / "market_handlers.py",
    COMMANDS_ROOT / "compare.py",
    COMMANDS_ROOT / "dashboard.py",
    COMMANDS_ROOT / "quality_report.py",
    COMMANDS_ROOT / "benchmark.py",
    COMMANDS_ROOT / "validate_history.py",
    COMMANDS_ROOT / "certify.py",
    COMMANDS_ROOT / "doctor" / "__init__.py",
}

_BROKER_SESSION_RE = re.compile(r"\bBrokerSession\s*\(")
_DELEGATION_RE = re.compile(
    r"from\s+brokers\.(services|platform_ops)\s+import|from\s+interface\.ui\.services\.broker_ops\s+import|from\s+interface\.ui\.commands\._broker\s+import"
)


def _iter_py_files(root: Path) -> list[Path]:
    if not root.is_dir():
        return []
    return sorted(p for p in root.rglob("*.py") if p.is_file())


@pytest.mark.unit
class TestUiBrokerOpsDelegation:
    def test_commands_no_direct_broker_session(self) -> None:
        violations: list[str] = []
        for path in _iter_py_files(COMMANDS_ROOT):
            if path in _BROKER_SESSION_ALLOWLIST:
                continue
            text = path.read_text(encoding="utf-8")
            if _BROKER_SESSION_RE.search(text):
                violations.append(str(path.relative_to(PROJECT_ROOT)))
        assert not violations, "Direct BrokerSession() in UI commands:\n" + "\n".join(violations)

    def test_migrated_commands_import_broker_ops_or_services(self) -> None:
        missing: list[str] = []
        for path in _DELEGATION_REQUIRED:
            if not path.is_file():
                missing.append(f"{path.relative_to(PROJECT_ROOT)} (missing file)")
                continue
            text = path.read_text(encoding="utf-8")
            if not _DELEGATION_RE.search(text):
                missing.append(str(path.relative_to(PROJECT_ROOT)))
        assert not missing, "Commands missing broker_ops/brokers.services import:\n" + "\n".join(missing)
