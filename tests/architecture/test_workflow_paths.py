"""CI workflow path drift guard (TRANS-P3-003).

Every script/test path referenced in GitHub workflows must exist in the
working tree. Prevents silent CI failure from layout migrations.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = REPO_ROOT / ".github" / "workflows"

# Paths that are generated at runtime (not required to exist in tree).
_GENERATED_PREFIXES = (
    "docs/audits/",
    "reports/",
    "bandit",
    "safety",
    "junit",
    "certification",
    "flaky-",
    "coverage",
    "htmlcov/",
    "/tmp/",
)

# Regexes for path-like tokens in workflow YAML.
_PATH_PATTERNS = [
    re.compile(r"python\s+([^\s|;&]+\.py)"),
    re.compile(r"bash\s+([^\s|;&]+\.sh)"),
    re.compile(r"pytest\s+([^\s|;&]+)"),
    re.compile(r"tests/[a-zA-Z0-9_./-]+"),
    re.compile(r"scripts/[a-zA-Z0-9_./-]+\.py"),
    re.compile(r"scripts/[a-zA-Z0-9_./-]+\.sh"),
]


def _workflow_files() -> list[Path]:
    return sorted(WORKFLOWS.glob("*.yml"))


def _extract_path_candidates(content: str) -> set[str]:
    found: set[str] = set()
    for line in content.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        for pattern in _PATH_PATTERNS:
            for match in pattern.finditer(stripped):
                token = match.group(1) if match.lastindex else match.group(0)
                token = token.strip("\"'")
                if any(x in token for x in ("$", "{{", "}}", "*", "||", "&&")):
                    continue
                if token.endswith(".py") or token.endswith(".sh"):
                    found.add(token)
                elif token.startswith("tests/"):
                    found.add(token.rstrip("/"))
    return found


def _exists_in_repo(path_str: str) -> bool:
    if any(path_str.startswith(p) for p in _GENERATED_PREFIXES):
        return True
    if path_str.startswith("src/"):
        return (REPO_ROOT / path_str).exists()
    candidate = REPO_ROOT / path_str
    if candidate.exists():
        return True
    # pytest targets may be directories or files with markers — allow dirs.
    if "/" in path_str and not path_str.endswith(".py"):
        return candidate.exists()
    return False


@pytest.mark.architecture
def test_workflow_referenced_paths_exist() -> None:
    """All script/test paths in workflows resolve in the working tree."""
    missing: list[tuple[str, str]] = []
    for wf in _workflow_files():
        content = wf.read_text(encoding="utf-8")
        for path_str in sorted(_extract_path_candidates(content)):
            if not _exists_in_repo(path_str):
                missing.append((wf.name, path_str))
    assert not missing, "Stale CI paths:\n" + "\n".join(f"  {wf}: {path}" for wf, path in missing)


@pytest.mark.architecture
def test_known_layout_migrations_not_referenced() -> None:
    """Forbidden legacy paths must not reappear in workflows."""
    legacy = [
        "brokers/providers/dhan/tests/",
        "brokers/providers/upstox/tests/",
        "scripts/check_constants_placement.py",
        "scripts/capability_report.py",
        "scripts/detect_flaky_tests.py",
        "scripts/dhan_regression_report.py",
        "scripts/revalidate_upstox_known_issues.py",
        "scripts/run_mutation_tests.sh",
        "python -m scripts.verify_event_replay",
        "tests/stress/",
        "tests/regression/test_memory_leaks.py",
        "application/oms/tests",
        "cli/tests/",
    ]
    hits: list[tuple[str, str]] = []
    for wf in _workflow_files():
        content = wf.read_text(encoding="utf-8")
        for leg in legacy:
            if leg in content:
                hits.append((wf.name, leg))
    assert not hits, "Legacy paths still referenced:\n" + "\n".join(
        f"  {wf}: {leg}" for wf, leg in hits
    )
