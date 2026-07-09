"""Domain purity: no top-level pandas imports in production domain modules."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
DOMAIN = ROOT / "src" / "domain"

# Modules that may lazy-import pandas inside functions (export adapters only)
# — still must NOT top-level import.
ALLOWED_LAZY_HINT = {
    "to_dataframe",
    "from_dataframe",
    "calculate_frame",
    "resample",
    "as_dataframe",
}


def _top_level_pandas_imports(path: Path) -> list[int]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    lines: list[int] = []
    for node in tree.body:
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "pandas" or alias.name.startswith("pandas."):
                    lines.append(node.lineno)
        elif isinstance(node, ast.ImportFrom) and node.module:
            if node.module == "pandas" or node.module.startswith("pandas."):
                lines.append(node.lineno)
    return lines


def test_domain_prod_has_no_toplevel_pandas() -> None:
    files = [
        f
        for f in DOMAIN.rglob("*.py")
        if "__pycache__" not in f.parts and "tests" not in f.parts
    ]
    assert files, f"no domain files under {DOMAIN}"
    violations: list[str] = []
    for f in files:
        for lineno in _top_level_pandas_imports(f):
            violations.append(f"{f.relative_to(ROOT)}:{lineno}")
    assert not violations, (
        "Top-level pandas imports forbidden in domain (use lazy import in "
        f"export adapters only): {violations}"
    )


def test_core_domain_modules_import_without_prior_pandas() -> None:
    """Import core modules with pandas absent from sys.modules (cold start)."""
    import importlib
    import sys

    # Drop pandas if already loaded so we prove these modules don't need it
    for name in list(sys.modules):
        if name == "pandas" or name.startswith("pandas."):
            del sys.modules[name]
        if name.startswith("domain"):
            del sys.modules[name]

    src = str(ROOT / "src")
    if src not in sys.path:
        sys.path.insert(0, src)

    core = [
        "domain.instruments.instrument",
        "domain.indicators.rsi",
        "domain.indicators.atr",
        "domain.indicators.vwap",
        "domain.indicators.macd",
        "domain.indicators.indicators",
        "domain.services.history",
        "domain.services.analytics",
        "domain.ports.market_data",
        "domain.ports.protocols",
    ]
    for modname in core:
        importlib.import_module(modname)

    assert "pandas" not in sys.modules, (
        "Importing core domain modules must not load pandas into sys.modules"
    )
