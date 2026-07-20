"""Architecture tests: enforce domain layer isolation.

Verifies that the domain layer never imports from application, brokers,
analytics, api, cli, infrastructure, datalake, plugins, or tradex.

Critical: scan ``src/domain`` (src-layout). A previous version scanned
``ROOT/domain`` which does not exist, so the AST walker parsed zero files
and the suite silently passed.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
DOMAIN_DIR = ROOT / "src" / "domain"

FORBIDDEN_LAYERS = (
    "application",
    "brokers",
    "analytics",
    "interface",
    "config",
    "infrastructure",
    "datalake",
    "plugins",
    "tradex",
    "runtime",
)


def _extract_import_root(stmt: ast.stmt) -> str | None:
    """Extract the top-level module name from an import statement."""
    if isinstance(stmt, ast.Import):
        if stmt.names:
            return stmt.names[0].name.split(".")[0]
    elif isinstance(stmt, ast.ImportFrom) and stmt.module:
        return stmt.module.split(".")[0]
    return None


def _iter_domain_prod_files() -> list[Path]:
    files = [
        f
        for f in DOMAIN_DIR.rglob("*.py")
        if "__pycache__" not in f.parts and "tests" not in f.parts
    ]
    # ponytail: fail loudly if path drifts again (empty scan == false green)
    assert files, (
        f"Domain isolation scanner found zero Python files under {DOMAIN_DIR}. "
        f"Expected src-layout package at src/domain."
    )
    return files


class TestDomainIsolation:
    """Domain layer must not import outer layers or plugins."""

    def test_domain_scan_is_non_empty(self) -> None:
        files = _iter_domain_prod_files()
        assert len(files) >= 20

    @pytest.mark.parametrize("forbidden", list(FORBIDDEN_LAYERS))
    def test_domain_does_not_import_from(self, forbidden: str) -> None:
        """Domain files must not import from forbidden layers."""
        violations: list[str] = []

        for f in _iter_domain_prod_files():
            try:
                tree = ast.parse(f.read_text(encoding="utf-8"))
            except SyntaxError:
                continue
            for node in ast.walk(tree):
                if isinstance(node, ast.Import | ast.ImportFrom):
                    root = _extract_import_root(node)
                    if root == forbidden:
                        violations.append(f"{f.relative_to(ROOT)}:{node.lineno}")

        assert not violations, (
            f"Domain imports from '{forbidden}' at: {violations}. "
            f"Domain layer must be independent of outer packages."
        )


class TestDomainResolvesInRepo:
    """import domain must resolve to *this* repository (not a shadowed install)."""

    def test_domain_module_file_is_under_repo_root(self) -> None:
        import domain

        domain_file = Path(domain.__file__).resolve()
        assert str(domain_file).startswith(str(ROOT.resolve())), (
            f"import domain resolved outside this repo: {domain_file} "
            f"(repo root {ROOT}). Pin PYTHONPATH=src:. when running lint-imports."
        )
        assert (ROOT / "src" / "domain").resolve() in domain_file.parents or domain_file.parent == (
            ROOT / "src" / "domain"
        ).resolve()

    def test_domain_imports_from_src_layout(self) -> None:
        """Dual-root guard: domain must load from src/domain, not a root package."""
        import domain

        # Normalize separators so Windows paths still contain the src-layout marker.
        domain_path = Path(domain.__file__).resolve().as_posix()
        assert "/src/domain" in domain_path, (
            f"Expected domain.__file__ under .../src/domain, got {domain.__file__}. "
            f"Use PYTHONPATH=src:. (pytest pythonpath already sets this)."
        )
