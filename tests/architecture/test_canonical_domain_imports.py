"""Architecture — canonical domain import paths, no facade imports (REF-9).

Rule: import every domain type from its owning submodule
(``from domain.enums import Side``), never from the ``domain`` mega-facade or
the ``domain.types`` secondary facade. The ``domain/__init__.py`` facade is
stripped to ``__version__`` only; ``domain/types.py`` is a re-export shim that
new code must not use.
"""

from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_SCRIPT = _PROJECT_ROOT / "scripts" / "ci" / "check_canonical_domain_imports.py"


@pytest.mark.architecture
def test_ci_canonical_domain_imports_check_passes() -> None:
    proc = subprocess.run(
        [sys.executable, str(_SCRIPT)], cwd=_PROJECT_ROOT, capture_output=True, text=True
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr


@pytest.mark.architecture
def test_canonical_domain_imports_script_flags_new_facade_import(tmp_path) -> None:
    """A brand-new ``from domain import X`` must fail CI."""
    offender = _PROJECT_ROOT / "src" / "domain" / "_test_ref9_offender.py"
    offender.write_text("from domain import Side\n", encoding="utf-8")
    try:
        proc = subprocess.run(
            [sys.executable, str(_SCRIPT)], cwd=_PROJECT_ROOT, capture_output=True, text=True
        )
        assert proc.returncode == 1, proc.stdout
        assert "_test_ref9_offender.py" in proc.stderr
    finally:
        offender.unlink(missing_ok=True)


@pytest.mark.architecture
def test_no_domain_facade_imports() -> None:
    """AST-based check: no file in src/ may use `from domain import X` (except __version__)."""
    src = _PROJECT_ROOT / "src"
    violations = []
    for py in src.rglob("*.py"):
        if "__pycache__" in str(py) or "tests" in str(py):
            continue
        # Allow the facades themselves
        rel = py.relative_to(_PROJECT_ROOT).as_posix()
        if rel in ("src/domain/__init__.py", "src/domain/types.py"):
            continue
        try:
            tree = ast.parse(py.read_text())
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module == "domain":
                if not any(alias.name == "__version__" for alias in node.names):
                    violations.append(str(py))
    assert violations == [], f"Facade imports found: {violations}"


@pytest.mark.architecture
def test_no_domain_types_facade_imports() -> None:
    """AST-based check: no file in src/ may use `from domain.types import X`."""
    src = _PROJECT_ROOT / "src"
    violations = []
    for py in src.rglob("*.py"):
        if "__pycache__" in str(py) or "tests" in str(py):
            continue
        rel = py.relative_to(_PROJECT_ROOT).as_posix()
        if rel == "src/domain/types.py":
            continue
        try:
            tree = ast.parse(py.read_text())
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module == "domain.types":
                violations.append(str(py))
    assert violations == [], f"domain.types imports found: {violations}"


@pytest.mark.architecture
def test_domain_init_only_exports_version() -> None:
    """domain/__init__.py should only define __version__, no re-exports."""
    init_text = (_PROJECT_ROOT / "src" / "domain" / "__init__.py").read_text(encoding="utf-8")
    assert "__version__" in init_text
    assert "from domain" not in init_text
    assert "__all__" not in init_text
