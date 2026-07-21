"""Ratchet: BrokerSession public trading/subscribe surface is gateway-only.

Domain ``Session.buy`` remains the OMS composition-root spine (used by
``BrokerGateway.place_order``). ``Instrument.buy`` / ``.subscribe`` are removed.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
_SRC = _ROOT / "src"


def _py_files(base: Path) -> list[Path]:
    return [p for p in base.rglob("*.py") if "__pycache__" not in p.parts]


@pytest.mark.architecture
def test_broker_session_has_no_buy_or_subscribe() -> None:
    from brokers.session.broker_session import BrokerSession

    assert not hasattr(BrokerSession, "buy")
    assert not hasattr(BrokerSession, "subscribe")
    assert not hasattr(BrokerSession, "quote")
    assert hasattr(BrokerSession, "gateway")


@pytest.mark.architecture
def test_instrument_has_no_buy_sell_subscribe_cancel_modify() -> None:
    from domain.instruments.instrument import Equity

    for name in ("buy", "sell", "subscribe", "cancel", "modify"):
        assert not hasattr(Equity, name), f"Instrument.{name} must be deleted (use gateway)"


@pytest.mark.architecture
def test_no_broker_session_buy_calls_in_tradex_or_interface() -> None:
    """Reject ``.buy(`` call sites under tradex / brokers.session facades."""
    violations: list[str] = []
    for root_name in ("tradex", "brokers/session"):
        root = _SRC / root_name
        if not root.exists():
            continue
        for path in _py_files(root):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                    if node.func.attr == "buy":
                        rel = path.relative_to(_SRC)
                        violations.append(f"{rel}:{node.lineno}")
    assert not violations, "BrokerSession.buy call sites:\n" + "\n".join(violations)


@pytest.mark.architecture
def test_no_broker_session_buy_or_subscribe_in_brokers_services() -> None:
    """brokers/services must use gateway, not removed BrokerSession.buy/subscribe."""
    root = _SRC / "brokers" / "services"
    if not root.exists():
        pytest.skip("brokers/services missing")
    violations: list[str] = []
    for path in _py_files(root):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)):
                continue
            if node.func.attr not in {"buy", "sell", "subscribe", "unsubscribe"}:
                continue
            owner = node.func.value
            if (
                isinstance(owner, ast.Attribute)
                and owner.attr == "gateway"
                and node.func.attr in {"subscribe", "unsubscribe"}
            ):
                continue
            rel = path.relative_to(_SRC)
            violations.append(f"{rel}:{node.lineno}.{node.func.attr}")
    assert not violations, "Use session.gateway in brokers/services:\n" + "\n".join(
        violations
    )
