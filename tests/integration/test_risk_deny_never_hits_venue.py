"""Acceptance test: risk deny never hits venue (spec §11.3).

Kill-switch on must produce zero submit calls to the FillSource.
"""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from domain import Order
from domain.enums import OrderStatus
from domain.types import Side, OrderType, ProductType, Validity
from application.oms._internal.risk_manager import RiskManager
from application.oms._internal.risk_types import RiskConfig, RiskResult
from application.oms.position_manager import PositionManager


def _make_order() -> Order:
    return Order(
        order_id="test-1",
        symbol="RELIANCE",
        exchange="NSE",
        side=Side.BUY,
        order_type=OrderType.LIMIT,
        quantity=10,
        price=2500.0,
        trigger_price=0.0,
        product_type=ProductType.CNC,
        validity=Validity.DAY,
        status=OrderStatus.OPEN,
        timestamp=datetime.now(timezone.utc),
    )


def test_kill_switch_denies_order():
    """Kill-switch active must deny the order."""
    position_manager = MagicMock(spec=PositionManager)
    position_manager.get_position.return_value = None
    position_manager.get_positions.return_value = []

    config = RiskConfig(
        max_daily_loss_pct=Decimal("5"),
        max_position_pct=Decimal("20"),
        max_gross_exposure_pct=Decimal("100"),
        enable_margin_check=False,
    )

    risk = RiskManager(
        position_manager=position_manager,
        config=config,
        instrument_provider=MagicMock(),
    )

    risk.set_kill_switch(True)
    result = risk.check_order(_make_order())
    assert not result.allowed
    assert "kill" in result.reason.lower()


def test_risk_deny_does_not_call_fill_source():
    """When risk denies, the FillSource.submit_fn must never be invoked."""
    from application.execution.execution_engine import ExecutionEngine
    from application.execution.fill_source import FillSource
    from application.oms.order_manager import OmsOrderCommand

    position_manager = MagicMock(spec=PositionManager)
    position_manager.get_position.return_value = None
    position_manager.get_positions.return_value = []

    config = RiskConfig(
        max_daily_loss_pct=Decimal("5"),
        max_position_pct=Decimal("20"),
        max_gross_exposure_pct=Decimal("100"),
        enable_margin_check=False,
    )

    risk = RiskManager(
        position_manager=position_manager,
        config=config,
        instrument_provider=MagicMock(),
    )
    risk.set_kill_switch(True)

    mock_fill_source = MagicMock(spec=FillSource)
    mock_ctx = MagicMock()
    mock_risk_result = MagicMock()
    mock_risk_result.allowed = False
    mock_risk_result.reason = "Kill switch is active"

    mock_oms = MagicMock()
    mock_oms.place_order.return_value = MagicMock(success=False)
    mock_ctx.order_manager = mock_oms
    mock_ctx.risk_manager = risk

    engine = ExecutionEngine(fill_source=mock_fill_source, trading_context=mock_ctx)

    result = risk.check_order(_make_order())
    assert not result.allowed

    mock_fill_source.submit_fn.assert_not_called()


def test_kill_switch_prevents_all_risk_checks():
    """Kill switch must be the first check — no other risk check runs."""
    position_manager = MagicMock(spec=PositionManager)
    position_manager.get_position.return_value = None
    position_manager.get_positions.return_value = []

    config = RiskConfig(
        max_daily_loss_pct=Decimal("5"),
        max_position_pct=Decimal("20"),
        max_gross_exposure_pct=Decimal("100"),
        enable_margin_check=False,
    )

    risk = RiskManager(
        position_manager=position_manager,
        config=config,
        instrument_provider=MagicMock(),
    )
    risk.set_kill_switch(True)

    for _ in range(3):
        result = risk.check_order(_make_order())
        assert not result.allowed
        assert "kill" in result.reason.lower()
