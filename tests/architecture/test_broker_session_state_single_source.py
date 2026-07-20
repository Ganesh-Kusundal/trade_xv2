"""Architecture ratchet — broker session FSM is defined only in domain."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
BROKERS = ROOT / "src" / "brokers"
CANONICAL = ROOT / "src" / "domain" / "ports" / "broker_session_state.py"


@pytest.mark.architecture
def test_broker_session_state_defined_in_domain_only() -> None:
    assert CANONICAL.is_file()


@pytest.mark.architecture
def test_no_parallel_broker_session_state_enum_in_brokers() -> None:
    """Brokers must not define a competing session-state enum."""
    forbidden_names = {"BrokerSessionState"}
    offenders: list[str] = []
    for path in BROKERS.rglob("*.py"):
        if "broker_session_state" in path.name:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and node.name in forbidden_names:
                offenders.append(str(path.relative_to(ROOT)))
    assert not offenders, f"Duplicate BrokerSessionState definitions: {offenders}"
