"""Forbid place_order calls outside the execution kernel.

ponytail: text heuristic on `.place_order(` under application/ excluding
execution/. Ceiling: misses aliased calls (`fn = gateway.place_order`),
dynamic getattr, and plugin paths (plugins/ is out of scope by design).
Upgrade: AST Call resolution + import graph degree when wiring grows.
"""

from __future__ import annotations

from pathlib import Path

_APP = Path(__file__).resolve().parents[2] / "src" / "application"
_PATTERN = ".place_order("


def test_no_place_order_outside_execution() -> None:
    violations: list[str] = []
    for path in sorted(_APP.rglob("*.py")):
        if "execution" in path.relative_to(_APP).parts:
            continue
        text = path.read_text(encoding="utf-8")
        if _PATTERN in text:
            violations.append(str(path.relative_to(_APP.parent)))
    assert not violations, (
        "order-path bypass (.place_order outside application/execution):\n"
        + "\n".join(violations)
    )
