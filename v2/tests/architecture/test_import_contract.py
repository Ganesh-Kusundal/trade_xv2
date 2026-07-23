"""Architecture import contracts — domain purity, application isolation, layering.

Enforces the dependency rule from context/architecture.md:
  domain/  → (nothing inward — stdlib + self only)
  application/ → domain only (no infrastructure/runtime/plugins/interface)
  infrastructure/ → domain + application (no runtime/interface/plugins)
  runtime/ → ALL layers (composition root)
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

_SRC = Path(__file__).resolve().parents[2] / "src"

# ---------------------------------------------------------------------------
# Layer definitions
# ---------------------------------------------------------------------------

_DOMAIN = _SRC / "domain"
_APPLICATION = _SRC / "application"
_INFRASTRUCTURE = _SRC / "infrastructure"
_RUNTIME = _SRC / "runtime"
_PLUGINS = _SRC / "plugins"
_INTERFACE = _SRC / "interface"

# Forbidden import roots per layer
_FORBIDDEN = {
    "domain": frozenset({"application", "infrastructure", "runtime", "interface", "plugins"}),
    "application": frozenset({"infrastructure", "runtime", "interface", "plugins"}),
    "infrastructure": frozenset({"runtime", "interface", "plugins"}),
}


def _imported_roots(tree: ast.AST) -> set[str]:
    """Extract top-level package names from import statements, excluding TYPE_CHECKING blocks."""
    tc_imports: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.If):
            test = node.test
            if (isinstance(test, ast.Name) and test.id == "TYPE_CHECKING") or (
                isinstance(test, ast.Attribute) and test.attr == "TYPE_CHECKING"
            ):
                for child in ast.walk(node):
                    if isinstance(child, (ast.Import, ast.ImportFrom)):
                        tc_imports.add(id(child))
    roots: set[str] = set()
    for node in ast.walk(tree):
        if id(node) in tc_imports:
            continue
        if isinstance(node, ast.Import):
            for alias in node.names:
                roots.add(alias.name.split(".", 1)[0])
        elif isinstance(node, ast.ImportFrom) and node.module:
            roots.add(node.module.split(".", 1)[0])
    return roots


def _check_layer_purity(layer_path: Path, forbidden: frozenset[str], layer_name: str) -> list[str]:
    """Scan all .py files in layer_path for forbidden imports."""
    violations: list[str] = []
    for path in sorted(layer_path.rglob("*.py")):
        text = path.read_text(encoding="utf-8")
        tree = ast.parse(text, filename=str(path))
        bad = _imported_roots(tree) & forbidden
        if bad:
            rel = path.relative_to(_SRC)
            violations.append(f"{rel}: imports {sorted(bad)}")
    return violations


# ---------------------------------------------------------------------------
# 1. Domain purity — no inward imports
# ---------------------------------------------------------------------------

class TestDomainPurity:
    def test_domain_does_not_import_application(self):
        violations = _check_layer_purity(_DOMAIN, {"application"}, "domain")
        assert not violations, "domain→application:\n" + "\n".join(violations)

    def test_domain_does_not_import_infrastructure(self):
        violations = _check_layer_purity(_DOMAIN, {"infrastructure"}, "domain")
        assert not violations, "domain→infrastructure:\n" + "\n".join(violations)

    def test_domain_does_not_import_runtime(self):
        violations = _check_layer_purity(_DOMAIN, {"runtime"}, "domain")
        assert not violations, "domain→runtime:\n" + "\n".join(violations)

    def test_domain_does_not_import_plugins(self):
        violations = _check_layer_purity(_DOMAIN, {"plugins"}, "domain")
        assert not violations, "domain→plugins:\n" + "\n".join(violations)

    def test_domain_does_not_import_interface(self):
        violations = _check_layer_purity(_DOMAIN, {"interface"}, "domain")
        assert not violations, "domain→interface:\n" + "\n".join(violations)

    def test_domain_purity_combined(self):
        """Domain must import nothing from outer layers (stdlib + self only)."""
        violations = _check_layer_purity(_DOMAIN, _FORBIDDEN["domain"], "domain")
        assert not violations, "domain purity violated:\n" + "\n".join(violations)


# ---------------------------------------------------------------------------
# 2. Application isolation — no infrastructure/runtime/plugins imports
# ---------------------------------------------------------------------------

class TestApplicationIsolation:
    def test_application_does_not_import_infrastructure(self):
        violations = _check_layer_purity(_APPLICATION, {"infrastructure"}, "application")
        assert not violations, "application→infrastructure:\n" + "\n".join(violations)

    def test_application_does_not_import_runtime(self):
        violations = _check_layer_purity(_APPLICATION, {"runtime"}, "application")
        assert not violations, "application→runtime:\n" + "\n".join(violations)

    def test_application_does_not_import_plugins(self):
        violations = _check_layer_purity(_APPLICATION, {"plugins"}, "application")
        assert not violations, "application→plugins:\n" + "\n".join(violations)

    def test_application_does_not_import_interface(self):
        violations = _check_layer_purity(_APPLICATION, {"interface"}, "application")
        assert not violations, "application→interface:\n" + "\n".join(violations)

    def test_application_isolation_combined(self):
        """Application may only import domain (no infra/runtime/plugins/interface)."""
        violations = _check_layer_purity(_APPLICATION, _FORBIDDEN["application"], "application")
        assert not violations, "application isolation violated:\n" + "\n".join(violations)


# ---------------------------------------------------------------------------
# 3. Infrastructure isolation — no runtime/plugins/interface imports
# ---------------------------------------------------------------------------

class TestInfrastructureIsolation:
    def test_infrastructure_does_not_import_runtime(self):
        violations = _check_layer_purity(_INFRASTRUCTURE, {"runtime"}, "infrastructure")
        assert not violations, "infrastructure→runtime:\n" + "\n".join(violations)

    def test_infrastructure_does_not_import_plugins(self):
        violations = _check_layer_purity(_INFRASTRUCTURE, {"plugins"}, "infrastructure")
        assert not violations, "infrastructure→plugins:\n" + "\n".join(violations)

    def test_infrastructure_does_not_import_interface(self):
        violations = _check_layer_purity(_INFRASTRUCTURE, {"interface"}, "infrastructure")
        assert not violations, "infrastructure→interface:\n" + "\n".join(violations)

    def test_infrastructure_isolation_combined(self):
        """Infrastructure may import domain + application only."""
        violations = _check_layer_purity(_INFRASTRUCTURE, _FORBIDDEN["infrastructure"], "infrastructure")
        assert not violations, "infrastructure isolation violated:\n" + "\n".join(violations)


# ---------------------------------------------------------------------------
# 4. No god classes — LOC ceiling
# ---------------------------------------------------------------------------

class TestGodClassSize:
    _MAX_LINES = 500

    def test_no_src_file_exceeds_500_lines(self):
        oversized: list[str] = []
        for path in sorted(_SRC.rglob("*.py")):
            n = sum(1 for _ in path.open(encoding="utf-8"))
            if n > self._MAX_LINES:
                oversized.append(f"{path.relative_to(_SRC)}: {n} lines")
        assert not oversized, "god-class LOC ceiling exceeded:\n" + "\n".join(oversized)


# ---------------------------------------------------------------------------
# 5. No bypass order paths — .place_order outside execution/
# ---------------------------------------------------------------------------

class TestNoBypassOrderPath:
    def test_no_place_order_outside_execution(self):
        violations: list[str] = []
        for path in sorted(_APPLICATION.rglob("*.py")):
            if "execution" in path.relative_to(_APPLICATION).parts:
                continue
            text = path.read_text(encoding="utf-8")
            if ".place_order(" in text:
                violations.append(str(path.relative_to(_APPLICATION.parent)))
        assert not violations, (
            "order-path bypass (.place_order outside application/execution):\n"
            + "\n".join(violations)
        )


# ---------------------------------------------------------------------------
# 6. No application → plugins (composition root only)
# ---------------------------------------------------------------------------

class TestNoAppToPlugins:
    def test_application_does_not_import_concrete_plugins(self):
        violations = _check_layer_purity(_APPLICATION, {"plugins"}, "application")
        assert not violations, "application→plugins leak:\n" + "\n".join(violations)
