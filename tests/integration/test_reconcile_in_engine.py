"""Task 6 (B2): Hot-path reconciliation inside ExecutionEngine."""

from unittest.mock import MagicMock

from application.execution.execution_engine import ExecutionEngine
from application.execution.fill_source import SimulatedFillSource


def test_execution_engine_has_apply_mass_status():
    """ExecutionEngine must have apply_mass_status for hot-path reconcile."""
    ctx = MagicMock()
    ctx.order_manager = MagicMock()
    engine = ExecutionEngine(fill_source=SimulatedFillSource(), trading_context=ctx)
    assert hasattr(engine, "apply_mass_status")


def test_apply_mass_status_returns_drift_items():
    """apply_mass_status should return a list of drift items."""
    ctx = MagicMock()
    ctx.order_manager = MagicMock()
    ctx.order_manager.get_order.return_value = None
    engine = ExecutionEngine(fill_source=SimulatedFillSource(), trading_context=ctx)

    broker_order = MagicMock()
    broker_order.order_id = "broker-1"

    drift = engine.apply_mass_status(orders=[broker_order])
    assert isinstance(drift, list)
    assert len(drift) > 0
    assert drift[0]["severity"] == "HIGH"


def test_apply_mass_status_with_empty_snapshot():
    """Empty snapshot should return no drift."""
    ctx = MagicMock()
    ctx.order_manager = MagicMock()
    engine = ExecutionEngine(fill_source=SimulatedFillSource(), trading_context=ctx)

    drift = engine.apply_mass_status()
    assert drift == []
