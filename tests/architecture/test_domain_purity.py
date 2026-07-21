"""Architecture — domain layer must contain only entities, VOs, enums, ports.

Orchestration classes (Pipeline, Orchestrator, Engine, Projector) must not
live in src/domain/. REF-10 moved them to application/services/; domain
modules that still reference these names are backward-compat re-export shims
that must not define new classes.

Allowed exceptions:
- Files under domain/ports/ (Protocol definitions are legitimate domain)
- Files under domain/analytics/ (pure math/statistics, no orchestration)
"""

from __future__ import annotations

import ast
from pathlib import Path

SRC = Path(__file__).resolve().parents[2] / "src"
DOMAIN_DIR = SRC / "domain"

ORCHESTRATION_PATTERNS = ["Pipeline", "Orchestrator", "Engine", "Projector"]

# Subdirectories that legitimately contain domain-acceptable "Engine" names
ALLOWED_SUBDIRS = {"ports", "analytics"}


def test_domain_has_no_orchestration_classes() -> None:
    violations: list[str] = []
    for py in DOMAIN_DIR.rglob("*.py"):
        if "__pycache__" in str(py):
            continue
        # Skip legitimate subdirectories (ports, analytics)
        try:
            rel = py.relative_to(DOMAIN_DIR)
        except ValueError:
            continue
        if rel.parts and rel.parts[0] in ALLOWED_SUBDIRS:
            continue
        try:
            tree = ast.parse(py.read_text())
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                for pattern in ORCHESTRATION_PATTERNS:
                    if pattern in node.name:
                        violations.append(f"{py.name}:{node.name}")
    assert violations == [], f"Orchestration classes in domain: {violations}"
