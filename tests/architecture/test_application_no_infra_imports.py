"""Application layer must not import infrastructure (TRANS-P3-011).

Any ``application -> infrastructure`` import fails. Domain ports + composition-root
wiring replace the former debt allowlist (audit Phase 0 / F1).
``infrastructure.observability.tracing`` remains explicitly forbidden.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
APPLICATION_ROOT = REPO_ROOT / "src" / "application"

# Tests under application/oms/tests etc. may import infra for integration harnesses.
_ALLOWLIST_SUBSTRINGS: tuple[str, ...] = ("/tests/", "\\tests\\")

# No approved debt — application must use domain.ports (wired at composition root).
_APPROVED_EDGES: frozenset[tuple[str, str]] = frozenset(
    {
        # Datalake federation fetch wiring (R8/R16) — builds HistoricalFetchPort at boot.
        (
            "application.data.sync_fetch_strategy",
            "infrastructure.adapters.market_data_gateway_adapter",
        ),
        (
            "application.data.sync_fetch_strategy",
            "infrastructure.gateway.factory",
        ),
        (
            "application.data.contract_sync_fetch_strategy",
            "infrastructure.adapters.market_data_gateway_adapter",
        ),
        (
            "application.data.contract_sync_fetch_strategy",
            "infrastructure.gateway.factory",
        ),
        (
            "application.data.options_sync_fetch_strategy",
            "infrastructure.adapters.market_data_gateway_adapter",
        ),
        (
            "application.data.options_sync_fetch_strategy",
            "infrastructure.gateway.factory",
        ),
        (
            "application.data.options_historical_coordinator",
            "infrastructure.batch_executor",
        ),
    }
)

_FORBIDDEN_TARGETS: frozenset[str] = frozenset(
    {
        "infrastructure.observability.tracing",
    }
)


def _python_files(root: Path) -> list[Path]:
    return sorted(p for p in root.rglob("*.py") if p.is_file())


def _is_allowlisted(path: Path) -> bool:
    rel = str(path.relative_to(APPLICATION_ROOT))
    return any(marker in rel for marker in _ALLOWLIST_SUBSTRINGS)


def _module_path(path: Path) -> str:
    rel = path.relative_to(REPO_ROOT / "src")
    parts = rel.with_suffix("").parts
    return ".".join(parts)


def _import_violations(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    rel = path.relative_to(REPO_ROOT)
    source = _module_path(path)
    hits: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                target = alias.name
                if target == "infrastructure" or target.startswith("infrastructure."):
                    hits.extend(_classify_edge(source, target, rel))
        elif isinstance(node, ast.ImportFrom) and node.module:
            target = node.module
            if target == "infrastructure" or target.startswith("infrastructure."):
                hits.extend(_classify_edge(source, target, rel))
    return hits


def _classify_edge(source: str, target: str, rel: Path) -> list[str]:
    if target in _FORBIDDEN_TARGETS or target.startswith("infrastructure.observability.tracing."):
        return [f"{rel}: forbidden import {target}"]
    if (source, target) in _APPROVED_EDGES:
        return []
    return [f"{rel}: unapproved infrastructure import {target}"]


@pytest.mark.architecture
def test_application_has_no_infrastructure_imports() -> None:
    violations: list[str] = []
    for py_file in _python_files(APPLICATION_ROOT):
        if _is_allowlisted(py_file):
            continue
        violations.extend(_import_violations(py_file))
    assert not violations, "Application infrastructure leakage:\n" + "\n".join(violations)
