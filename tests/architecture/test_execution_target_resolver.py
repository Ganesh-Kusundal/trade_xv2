"""Architecture ratchet — execution target resolution lives in runtime only.

Constitution: ``docs/constitution/06-reference-architecture.md``,
``02a-runtime-execution-model.md`` §5.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_execution_target_resolver_module_exists() -> None:
    resolver = ROOT / "src/runtime/execution_target.py"
    assert resolver.is_file(), "runtime/execution_target.py must exist"


def test_domain_execution_target_port_exists() -> None:
    port = ROOT / "src/domain/ports/execution_target.py"
    assert port.is_file(), "domain ExecutionTarget port must exist"


def test_create_execution_adapter_delegates_to_runtime() -> None:
    """oms_backtest_adapter must not contain inline mode branches."""
    path = ROOT / "src/application/execution/oms_backtest_adapter.py"
    source = path.read_text(encoding="utf-8")
    assert "resolve_simulated_oms_adapter" in source
    assert 'mode == "paper"' not in source
    assert 'mode == "replay"' not in source
    assert "mode.lower()" not in source


def test_runtime_resolver_exports_kind_enum() -> None:
    source = (ROOT / "src/runtime/execution_target.py").read_text(encoding="utf-8")
    assert "ExecutionTargetKind" in source
    assert "resolve_execution_target" in source
