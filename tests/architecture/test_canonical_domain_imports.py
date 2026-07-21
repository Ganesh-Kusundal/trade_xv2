"""Architecture — canonical domain import paths, no new facade imports (REF-9).

Rule: import every domain type from its owning submodule
(``from domain.enums import Side``), never from the ``domain`` mega-facade or
the ``domain.types`` secondary facade. Enforced by
``scripts/ci/check_canonical_domain_imports.py`` against a grandfathered
baseline ledger so pre-existing debt doesn't block new callers while new
violations are still caught.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_SCRIPT = _PROJECT_ROOT / "scripts" / "ci" / "check_canonical_domain_imports.py"
_LEDGER = _PROJECT_ROOT / "docs" / "superpowers" / "ledgers" / "domain-facade-import-baseline.txt"


@pytest.mark.architecture
def test_ci_canonical_domain_imports_check_passes() -> None:
    proc = subprocess.run(
        [sys.executable, str(_SCRIPT)], cwd=_PROJECT_ROOT, capture_output=True, text=True
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr


@pytest.mark.architecture
def test_canonical_domain_imports_script_flags_new_facade_import(tmp_path) -> None:
    """A brand-new ``from domain import X`` (outside the baseline) must fail CI."""
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
def test_domain_init_and_types_facade_self_imports_are_allowed() -> None:
    """The facades themselves import from their own owning submodules — allowed."""
    init_text = (_PROJECT_ROOT / "src" / "domain" / "__init__.py").read_text(encoding="utf-8")
    types_text = (_PROJECT_ROOT / "src" / "domain" / "types.py").read_text(encoding="utf-8")
    assert "from domain import " not in init_text
    assert "from domain import " not in types_text


@pytest.mark.architecture
def test_baseline_ledger_exists_and_is_nonempty() -> None:
    assert _LEDGER.exists(), f"Missing REF-9 baseline ledger: {_LEDGER}"
    entries = [
        line.strip()
        for line in _LEDGER.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]
    assert entries, "Baseline ledger should list grandfathered facade-import files"


@pytest.mark.architecture
def test_code_standards_documents_canonical_import_rule() -> None:
    text = (_PROJECT_ROOT / "context" / "code-standards.md").read_text(encoding="utf-8")
    assert "from domain.enums import Side" in text
    assert "domain.types" in text


@pytest.mark.architecture
def test_domain_init_facade_carries_deprecation_notice() -> None:
    init_text = (_PROJECT_ROOT / "src" / "domain" / "__init__.py").read_text(encoding="utf-8")
    assert "DEPRECATED" in init_text
