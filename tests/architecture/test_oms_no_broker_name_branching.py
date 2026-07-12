"""Architecture guard: OMS must stay broker-agnostic (DR-B1).

The OMS may NOT branch on concrete broker **name** strings
(``if broker == "dhan"``) nor probe gateway internals
(``getattr(gw, "_broker")`` / ``"_conn"`` / ``extended``). Broker-specific
extended-order behaviour lives behind
:class:`domain.extensions.extended_order.ExtendedOrderExecutor`, resolved
through ``BrokerExtensionRegistry.require(broker_id, ...)``.

This guard fails closed if any live broker name sneaks back into
``src/application/oms/`` — the headline acceptance criterion for DR-B1.
"""

from __future__ import annotations

import ast
import glob
import os

import pytest

OMS_DIR = os.path.join("src", "application", "oms")

# Live broker ids that must never be hard-coded / compared in the OMS.
# Synthetic ids ("paper", "datalake") are intentionally NOT listed: a
# fail-closed allowlist of *synthetic* brokers is the correct pattern
# (see session_bridge._NON_LIVE_BROKER_IDS).
LIVE_BROKER_NAMES = ("dhan", "upstox")

# Deprecated gateway-internal probes removed by DR-B1.
DEPRECATED_PROBES = ("_get_broker", "_get_conn", "_get_extended", "_require_broker")


def _oms_files() -> list[str]:
    pattern = os.path.join(OMS_DIR, "**", "*.py")
    return [f for f in glob.glob(pattern, recursive=True) if "__pycache__" not in f]


def _literal_string_compares(tree: ast.Module) -> list[str]:
    """Return 'eq'/'ne' comparisons against a live broker-name string literal."""
    hits: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Compare) and len(node.ops) == 1:
            op = node.ops[0]
            if isinstance(op, (ast.Eq, ast.NotEq)):
                for side in (node.left, *node.comparators):
                    if isinstance(side, ast.Constant) and isinstance(side.value, str):
                        if side.value in LIVE_BROKER_NAMES:
                            hits.append(side.value)
    return hits


def test_oms_has_no_live_broker_name_comparisons() -> None:
    violations: list[str] = []
    for path in _oms_files():
        with open(path, encoding="utf-8") as fh:
            tree = ast.parse(fh.read(), filename=path)
        for name in _literal_string_compares(tree):
            violations.append(f"{path}: compares against live broker name {name!r}")
    assert not violations, (
        "OMS compares against a hard-coded live broker name (DR-B1 violated):\n"
        + "\n".join(violations)
    )


def test_oms_has_no_deprecated_gateway_probes() -> None:
    violations: list[str] = []
    for path in _oms_files():
        with open(path, encoding="utf-8") as fh:
            source = fh.read()
        for probe in DEPRECATED_PROBES:
            if probe in source:
                violations.append(f"{path}: references deprecated probe {probe!r}")
    assert not violations, (
        "OMS references a deprecated gateway-internal probe (DR-B1 violated):\n"
        + "\n".join(violations)
    )
