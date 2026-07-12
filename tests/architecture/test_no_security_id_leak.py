"""Ban broker token fields at public boundaries (interface, CLI, MCP, services)."""

from __future__ import annotations

import re
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]

_SCAN_ROOTS = (
    PROJECT_ROOT / "src" / "interface",
    PROJECT_ROOT / "src" / "brokers" / "mcp",
    PROJECT_ROOT / "src" / "brokers" / "cli",
    PROJECT_ROOT / "src" / "brokers" / "services",
)

_BANNED = re.compile(
    r"""(?x)
    \bsecurity_id\b
    | \binstrument_token\b
    | ["']securityId["']
    | ["']Security ID["']
    """
)

_ALLOW_LINE = re.compile(r"ponytail:|#.*internal|deprecated|no broker token", re.I)


def _iter_py_files(root: Path) -> list[Path]:
    if not root.is_dir():
        return []
    return sorted(p for p in root.rglob("*.py") if p.is_file())


def _scan(path: Path) -> list[str]:
    hits: list[str] = []
    for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        if _ALLOW_LINE.search(line):
            continue
        if _BANNED.search(line):
            hits.append(f"{path.relative_to(PROJECT_ROOT)}:{i}: {line.strip()[:120]}")
    return hits


def test_public_surfaces_do_not_reference_broker_tokens() -> None:
    violations: list[str] = []
    for root in _SCAN_ROOTS:
        for path in _iter_py_files(root):
            violations.extend(_scan(path))
    assert not violations, "Broker token leakage at public boundary:\n" + "\n".join(violations)
