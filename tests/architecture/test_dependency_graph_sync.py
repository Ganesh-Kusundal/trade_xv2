"""Keep application→infrastructure debt allowlists in sync (TRANS-P3-011 extension).

``test_application_no_infra_imports._APPROVED_EDGES`` (AST enforcement) must match
production ``ignore_imports`` on the ``Application infrastructure separation``
contract in ``pyproject.toml`` (import-linter contract #10).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from tests.architecture.test_application_no_infra_imports import _APPROVED_EDGES

REPO_ROOT = Path(__file__).resolve().parents[2]
PYPROJECT = REPO_ROOT / "pyproject.toml"
DEPENDENCY_GRAPH = REPO_ROOT / "docs" / "architecture" / "DEPENDENCY_GRAPH.md"

_CONTRACT_NAME = "Application infrastructure separation"
_EDGE_RE = re.compile(r"^\s*\"(?P<source>[^\"]+)\s*->\s*(?P<target>[^\"]+)\"\s*,?\s*(?:#.*)?$")


def _parse_application_infra_ignore_imports(pyproject_text: str) -> frozenset[tuple[str, str]]:
    """Extract production debt edges from the named import-linter contract."""
    lines = pyproject_text.splitlines()
    in_contract = False
    in_ignore_imports = False
    edges: set[tuple[str, str]] = set()

    for line in lines:
        if line.strip() == f'name = "{_CONTRACT_NAME}"':
            in_contract = True
            in_ignore_imports = False
            continue

        if in_contract and line.startswith("[[tool.importlinter.contracts]]"):
            break

        if not in_contract:
            continue

        if line.strip().startswith("ignore_imports"):
            in_ignore_imports = True
            continue

        if in_ignore_imports:
            if line.strip().startswith("]"):
                break
            match = _EDGE_RE.match(line)
            if not match:
                continue
            source = match.group("source").strip()
            target = match.group("target").strip()
            if "tests" in source or ".*" in source or "**" in target:
                continue
            if not source.startswith("application."):
                continue
            if not (target == "infrastructure" or target.startswith("infrastructure.")):
                continue
            edges.add((source, target))

    if not edges and not _APPROVED_EDGES:
        return frozenset()
    if not edges:
        msg = f"No production application→infrastructure edges found for {_CONTRACT_NAME!r}"
        raise AssertionError(msg)
    return frozenset(edges)


@pytest.mark.architecture
def test_approved_edges_match_pyproject_application_infra_contract() -> None:
    pyproject_edges = _parse_application_infra_ignore_imports(PYPROJECT.read_text(encoding="utf-8"))
    missing_in_pyproject = _APPROVED_EDGES - pyproject_edges
    extra_in_pyproject = pyproject_edges - _APPROVED_EDGES
    assert not missing_in_pyproject and not extra_in_pyproject, (
        "Application infrastructure debt allowlist drift detected.\n"
        f"  In test _APPROVED_EDGES only: {sorted(missing_in_pyproject)}\n"
        f"  In pyproject.toml only: {sorted(extra_in_pyproject)}\n"
        "Update pyproject.toml, test_application_no_infra_imports.py, "
        "DEPENDENCY_RULES.md, and DEPENDENCY_GRAPH.md together."
    )


@pytest.mark.architecture
def test_dependency_graph_doc_exists() -> None:
    assert DEPENDENCY_GRAPH.is_file(), (
        f"Missing architecture doc: {DEPENDENCY_GRAPH.relative_to(REPO_ROOT)}"
    )
    text = DEPENDENCY_GRAPH.read_text(encoding="utf-8")
    assert "DEPENDENCY_RULES.md" in text
    assert "pyproject.toml" in text
    assert "Parallel execution waves" in text
