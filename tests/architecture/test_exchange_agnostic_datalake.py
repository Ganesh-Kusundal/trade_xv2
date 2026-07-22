"""ADR-005 — datalake reads exchange conventions only via exchange_registry."""

from __future__ import annotations

from pathlib import Path

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_DATALAKE_SRC = _PROJECT_ROOT / "src" / "datalake"


@pytest.mark.architecture
def test_datalake_does_not_import_nse_calendar_directly() -> None:
    """Production datalake code must use exchange_registry, not nse_calendar shim."""
    violations: list[str] = []
    skip = {"core/nse_calendar.py", "core/__init__.py"}
    for py_file in _DATALAKE_SRC.rglob("*.py"):
        rel = py_file.relative_to(_DATALAKE_SRC).as_posix()
        if rel in skip:
            continue
        text = py_file.read_text(encoding="utf-8")
        if "datalake.core.nse_calendar" in text or "from datalake.core import nse_calendar" in text:
            violations.append(rel)
    assert not violations, (
        "Direct nse_calendar imports in datalake/ — use datalake.exchange_registry:\n"
        + "\n".join(f"  {v}" for v in violations)
    )


@pytest.mark.architecture
def test_composition_wires_exchange_plugins() -> None:
    import inspect

    from runtime import composition

    src = inspect.getsource(composition.wire_domain_port_sinks)
    assert "wire_exchange_plugins" in src
