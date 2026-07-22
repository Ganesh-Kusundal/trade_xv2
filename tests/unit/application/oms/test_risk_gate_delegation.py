"""R9 — RiskManager delegates exposure limits to domain RiskGate."""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock

from application.oms._internal.risk_manager import RiskManager
from application.oms._internal.risk_types import RiskConfig
from application.oms.capital_provider import FixedCapitalProvider
from application.oms.position_manager import PositionManager
from domain import Order
from domain.enums import OrderStatus
from domain.risk.policy import KillSwitch as DomainKillSwitch
from domain.types import OrderType, ProductType, Side, Validity
from datetime import datetime, timezone


def _order(qty: int = 10, price: float = 2500.0) -> Order:
    return Order(
        order_id="r9-1",
        symbol="RELIANCE",
        exchange="NSE",
        side=Side.BUY,
        order_type=OrderType.LIMIT,
        quantity=qty,
        price=price,
        trigger_price=0.0,
        product_type=ProductType.CNC,
        validity=Validity.DAY,
        status=OrderStatus.OPEN,
        timestamp=datetime.now(timezone.utc),
    )


def test_risk_manager_always_has_domain_kill_switch():
    rm = RiskManager(
        position_manager=PositionManager(),
        config=RiskConfig(),
        capital_provider=FixedCapitalProvider(Decimal("1000000")),
    )
    assert isinstance(rm._domain_kill_switch, DomainKillSwitch)


def test_risk_gate_rejects_gross_exposure(monkeypatch):
    monkeypatch.delenv("TRADEX_RISK_LEGACY", raising=False)
    position_manager = MagicMock(spec=PositionManager)
    position_manager.get_position.return_value = None
    position_manager.get_positions.return_value = []

    config = RiskConfig(
        max_daily_loss_pct=Decimal("99"),
        max_position_pct=Decimal("100"),
        max_gross_exposure_pct=Decimal("1"),
        enable_margin_check=False,
    )
    rm = RiskManager(
        position_manager=position_manager,
        config=config,
        capital_provider=FixedCapitalProvider(Decimal("1000000")),
    )
    result = rm.check_order(_order(qty=5, price=2500.0))
    assert result.allowed is False
    assert "gross exposure" in (result.reason or "").lower()


def test_legacy_path_still_blocks_position_pct(monkeypatch):
    monkeypatch.setenv("TRADEX_RISK_LEGACY", "1")
    position_manager = MagicMock(spec=PositionManager)
    position_manager.get_position.return_value = None
    position_manager.get_positions.return_value = []

    config = RiskConfig(
        max_daily_loss_pct=Decimal("99"),
        max_position_pct=Decimal("1"),
        max_gross_exposure_pct=Decimal("100"),
        enable_margin_check=False,
    )
    rm = RiskManager(
        position_manager=position_manager,
        config=config,
        capital_provider=FixedCapitalProvider(Decimal("1000000")),
    )
    result = rm.check_order(_order(qty=500, price=2500.0))
    assert result.allowed is False
    assert "max position pct" in (result.reason or "").lower()
