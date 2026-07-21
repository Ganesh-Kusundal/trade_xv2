"""Architecture — paper/replay must not cross-import; use analytics.simulation (REF-14)."""

from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_PAPER = _PROJECT_ROOT / "src" / "analytics" / "paper"
_REPLAY = _PROJECT_ROOT / "src" / "analytics" / "replay"
_ANALYTICS = _PROJECT_ROOT / "src" / "analytics"
_FORBIDDEN_BROKER_PREFIXES = ("brokers.dhan", "brokers.upstox", "brokers.paper")


def _forbidden_imports(package: Path, forbidden_prefix: str) -> list[str]:
    offenders: list[str] = []
    for path in package.rglob("*.py"):
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                if node.module.startswith(forbidden_prefix):
                    offenders.append(f"{path.relative_to(_PROJECT_ROOT)} imports {node.module}")
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.startswith(forbidden_prefix):
                        offenders.append(
                            f"{path.relative_to(_PROJECT_ROOT)} imports {alias.name}"
                        )
    return offenders


@pytest.mark.architecture
def test_paper_does_not_import_replay_internals() -> None:
    offenders = _forbidden_imports(_PAPER, "analytics.replay")
    assert not offenders, "Paper must use analytics.simulation shared layer:\n" + "\n".join(offenders)


@pytest.mark.architecture
def test_replay_does_not_import_paper_internals() -> None:
    offenders = _forbidden_imports(_REPLAY, "analytics.paper")
    assert not offenders, "Replay must use analytics.simulation shared layer:\n" + "\n".join(offenders)


@pytest.mark.architecture
def test_analytics_does_not_import_concrete_brokers() -> None:
    offenders: list[str] = []
    for prefix in _FORBIDDEN_BROKER_PREFIXES:
        offenders.extend(_forbidden_imports(_ANALYTICS, prefix))
    assert not offenders, "Analytics must not import concrete broker modules:\n" + "\n".join(offenders)


@pytest.mark.architecture
def test_ci_analytics_cross_import_check_passes() -> None:
    script = _PROJECT_ROOT / "scripts" / "ci" / "check_analytics_cross_imports.py"
    proc = subprocess.run([sys.executable, str(script)], cwd=_PROJECT_ROOT, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr or proc.stdout


@pytest.mark.architecture
def test_importlinter_has_paper_replay_isolation_contract() -> None:
    text = (_PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert "Analytics paper/replay isolation" in text
    assert 'source_modules = ["analytics.paper"]' in text
    assert 'source_modules = ["analytics.replay"]' in text
