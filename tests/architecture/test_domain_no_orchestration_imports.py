"""Architecture — domain/ must not import from application/ (REF-10).

Orchestration logic (trading costs, simulation pipeline, reconciliation
engine) was moved to ``application/services/`` in REF-10. Domain retains
pure entities/value objects; application owns orchestration and may depend
on domain, but never the reverse.

A small set of domain modules remain as documented backward-compat
re-export shims pointing at their new ``application.services`` home (to
avoid breaking existing imports across the codebase). Those shims are the
*only* permitted exception and are tracked here explicitly; they must not
grow, and REF-13 will remove them once all call sites migrate.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[2] / "src"
DOMAIN_DIR = SRC / "domain"

# Documented backward-compat re-export shims created by REF-10. Each imports
# application.services solely to re-export names for old call sites; no new
# shim should be added to this list without an equivalent domain/__init__.py
# and progress-tracker note.
ALLOWED_SHIMS = {
    DOMAIN_DIR / "trading_costs.py",
    DOMAIN_DIR / "simulation_fill_pipeline.py",
    DOMAIN_DIR / "simulation_position_meta.py",
    DOMAIN_DIR / "portfolio_projection.py",
    DOMAIN_DIR / "reconciliation_engine.py",
}


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
def test_domain_does_not_import_application_except_documented_shims() -> None:
    violations = [
        path
        for path in _domain_python_files()
        if path not in ALLOWED_SHIMS and _imports_application(path.read_text())
    ]
    assert not violations, (
        "domain/ must not import from application/ (RC-2, REF-10). "
        f"Violating files: {[str(p.relative_to(SRC)) for p in violations]}"
    )


@pytest.mark.architecture
def test_documented_shims_still_exist_and_only_reexport() -> None:
    for path in ALLOWED_SHIMS:
        assert path.exists(), f"Expected backward-compat shim missing: {path}"
        source = path.read_text()
        assert _imports_application(source), f"Shim {path} no longer re-exports from application/"
        tree = ast.parse(source)
        defs = [n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.ClassDef))]
        assert not defs, (
            f"Shim {path} should only re-export names from application/services, "
            f"not define new logic: found {[d.name for d in defs]}"
        )


@pytest.mark.architecture
def test_allowed_shims_list_matches_reftarget_application_services() -> None:
    services_dir = SRC / "application" / "services"
    expected_targets = {
        "trading_costs_service.py",
        "simulation_orchestrator.py",
        "reconciliation_service.py",
    }
    missing = expected_targets - {p.name for p in services_dir.glob("*.py")}
    assert not missing, f"Expected application/services modules missing: {missing}"
