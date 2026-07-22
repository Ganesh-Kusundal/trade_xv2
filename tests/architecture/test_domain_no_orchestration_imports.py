"""Architecture — domain/ must not import from application/ (REF-10).

Orchestration logic (simulation constructs, reconciliation) lives in
``domain.simulation`` and ``application.services``. Domain retains pure
entities/value objects; application owns orchestration and may depend
on domain, but never the reverse.

The backward-compat re-export shims in ``domain/`` (``trading_costs.py``,
``portfolio_projection.py``, ``reconciliation_engine.py``,
``simulation_fill_pipeline.py``, ``simulation_position_meta.py``) have been
removed by the architectural audit — all call sites now import directly
from ``application.services.*`` or ``domain.simulation``.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[2] / "src"
DOMAIN_DIR = SRC / "domain"

# All backward-compat shims have been removed by the architectural audit.
ALLOWED_SHIMS: set[Path] = set()


def _imports_application(source: str) -> bool:
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            if any(alias.name.split(".")[0] == "application" for alias in node.names):
                return True
        elif isinstance(node, ast.ImportFrom):
            if node.module and node.module.split(".")[0] == "application":
                return True
    return False


def _domain_python_files() -> list[Path]:
    return sorted(p for p in DOMAIN_DIR.rglob("*.py") if "__pycache__" not in p.parts)


@pytest.mark.architecture
def test_domain_does_not_import_application() -> None:
    """No domain file may import from application/."""
    violations = [
        path
        for path in _domain_python_files()
        if _imports_application(path.read_text())
    ]
    assert not violations, (
        "domain/ must not import from application/ (RC-2, REF-10). "
        f"Violating files: {[str(p.relative_to(SRC)) for p in violations]}"
    )


@pytest.mark.architecture
def test_no_more_backward_compat_shims() -> None:
    """Verify no domain→application backward-compat shims remain."""
    shims_exist = [p for p in ALLOWED_SHIMS if p.exists()]
    assert not shims_exist, (
        f"Expected backward-compat shims to be deleted, but found: "
        f"{[str(p.relative_to(SRC)) for p in shims_exist]}"
    )
