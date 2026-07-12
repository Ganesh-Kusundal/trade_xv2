"""TRANS-P4-010 — verify/certify/doctor share one implementation path."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from brokers import platform_ops
from brokers.certification.suite import BrokerCertifier
from brokers.services import core as services_core

REPO_ROOT = Path(__file__).resolve().parents[2]

_CERT_OPS = ("run_verify", "run_certify", "run_doctor")
_FORBIDDEN_DIRECT_IMPORTS = frozenset({"BrokerCertifier"})


def _imports_symbol(path: Path, symbol: str) -> bool:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if symbol in {a.name for a in node.names}:
                return True
        if isinstance(node, ast.Import):
            if symbol in {a.name for a in node.names}:
                return True
    return False


@pytest.mark.architecture
@pytest.mark.parametrize("name", _CERT_OPS)
def test_platform_ops_reexports_services_core(name: str) -> None:
    assert getattr(platform_ops, name) is getattr(services_core, name)


@pytest.mark.architecture
def test_run_verify_uses_broker_certifier() -> None:
    import inspect

    src = inspect.getsource(services_core.run_verify)
    assert "BrokerCertifier" in src


@pytest.mark.architecture
@pytest.mark.parametrize(
    "rel_path",
    [
        "src/brokers/cli/broker.py",
        "src/interface/ui/services/broker_ops.py",
    ],
)
def test_frontends_do_not_import_broker_certifier_directly(rel_path: str) -> None:
    path = REPO_ROOT / rel_path
    for sym in _FORBIDDEN_DIRECT_IMPORTS:
        assert not _imports_symbol(path, sym), f"{rel_path} must not import {sym}"


@pytest.mark.architecture
def test_broker_certifier_is_canonical_entry() -> None:
    assert BrokerCertifier.__module__ == "brokers.certification.suite"