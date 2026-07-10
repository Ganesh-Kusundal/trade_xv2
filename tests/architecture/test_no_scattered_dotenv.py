"""Architecture test — verify _load_dotenv exists in exactly one place."""

from __future__ import annotations

import ast
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


def _find_function_definitions(root: Path, func_name: str) -> list[tuple[Path, str]]:
    hits: list[tuple[Path, str]] = []
    for py_file in root.rglob("*.py"):
        rel = str(py_file.relative_to(_PROJECT_ROOT))
        if "__pycache__" in rel or "venv" in rel:
            continue
        if "/tests/" in rel or rel.startswith("tests/"):
            continue
        try:
            tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=rel)
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == func_name:
                hits.append((py_file, node.name))
    return hits


def test_load_dotenv_is_single_source() -> None:
    """_load_dotenv must be defined in exactly one file: brokers/common/env_loader.py."""
    hits = _find_function_definitions(_PROJECT_ROOT / "src" / "brokers", "_load_dotenv")
    assert len(hits) <= 1, (
        f"_load_dotenv is defined in {len(hits)} files. "
        "It should exist only in brokers/common/env_loader.py:\n"
        + "\n".join(f"  {f.relative_to(_PROJECT_ROOT)}" for f, _ in hits)
    )
