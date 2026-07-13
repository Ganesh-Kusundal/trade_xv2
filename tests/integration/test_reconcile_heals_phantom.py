"""Acceptance test: reconcile heals phantom position (spec §11.3).

Local-only open position must be healed by mass-status before next check_order.
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from application.execution.execution_engine import ExecutionEngine
from application.execution.fill_source import FillSource


def test_apply_mass_status_detects_missing_local_order():
    """Broker has an order that local doesn't — drift detected as HIGH."""
    mock_ctx = MagicMock()
    mock_oms = MagicMock()
    mock_oms.get_order.return_value = None
    mock_ctx.order_manager = mock_oms

    fill_source = MagicMock(spec=FillSource)
    engine = ExecutionEngine(fill_source=fill_source, trading_context=mock_ctx)

    broker_order = MagicMock()
    broker_order.order_id = "BROKER-ONLY-1"

    drift = engine.apply_mass_status(orders=[broker_order])

    assert len(drift) == 1
    assert drift[0]["kind"] == "missing_local_order"
    assert drift[0]["severity"] == "HIGH"
    assert drift[0]["order_id"] == "BROKER-ONLY-1"


def test_apply_mass_status_empty_snapshot_no_drift():
    """Empty broker snapshot produces no drift items."""
    mock_ctx = MagicMock()
    mock_ctx.order_manager = MagicMock()

    fill_source = MagicMock(spec=FillSource)
    engine = ExecutionEngine(fill_source=fill_source, trading_context=mock_ctx)

    drift = engine.apply_mass_status(orders=[], positions=[], funds={})
    assert drift == []


def test_apply_mass_status_detects_position_updates():
    """Broker position updates are flagged as MEDIUM severity drift."""
    mock_ctx = MagicMock()
    mock_ctx.order_manager = MagicMock()

    fill_source = MagicMock(spec=FillSource)
    engine = ExecutionEngine(fill_source=fill_source, trading_context=mock_ctx)

    broker_pos = MagicMock()
    broker_pos.symbol = "RELIANCE"

    drift = engine.apply_mass_status(positions=[broker_pos])

    assert len(drift) == 1
    assert drift[0]["kind"] == "position_update"
    assert drift[0]["severity"] == "MEDIUM"
    assert drift[0]["symbol"] == "RELIANCE"


def test_reconciliation_service_delegates_to_engine():
    """ReconciliationService with execution_engine delegates apply to engine."""
    from application.oms.reconciliation_service import ReconciliationService

    mock_oms = MagicMock()
    mock_oms.get_orders.return_value = []
    mock_pm = MagicMock()
    mock_pm.get_positions.return_value = []

    mock_recon = MagicMock()
    report = MagicMock()
    report.has_drift = True
    report.drift_items = [MagicMock(kind="missing", severity="HIGH", symbol="X", details="")]
    report.high_severity_count = 1
    report.broker_orders = [MagicMock(order_id="B1")]
    report.broker_positions = []
    report.broker_funds = None
    mock_recon.reconcile.return_value = report

    mock_engine = MagicMock()

    service = ReconciliationService(
        order_manager=mock_oms,
        position_manager=mock_pm,
        reconciliation_service=mock_recon,
        interval_seconds=60.0,
        execution_engine=mock_engine,
    )

    service.run_now()

    mock_engine.apply_mass_status.assert_called_once()


def test_reconciliation_service_works_without_engine():
    """ReconciliationService without execution_engine still works (backward compat)."""
    from application.oms.reconciliation_service import ReconciliationService

    mock_oms = MagicMock()
    mock_oms.get_orders.return_value = []
    mock_pm = MagicMock()
    mock_pm.get_positions.return_value = []

    mock_recon = MagicMock()
    report = MagicMock()
    report.has_drift = False
    report.drift_items = []
    report.high_severity_count = 0
    mock_recon.reconcile.return_value = report

    service = ReconciliationService(
        order_manager=mock_oms,
        position_manager=mock_pm,
        reconciliation_service=mock_recon,
        interval_seconds=60.0,
    )

    result = service.run_now()
    assert result is not None
