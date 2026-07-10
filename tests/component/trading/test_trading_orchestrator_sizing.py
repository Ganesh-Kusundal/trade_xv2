"""ENG-003: position_size_pct is percent of equity, not share count."""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock

from application.oms.capital_provider import FixedCapitalProvider
from application.trading.trading_orchestrator import OrchestratorConfig, TradingOrchestrator
from domain.models.trading import SignalDTO


def _make_orchestrator(equity: Decimal = Decimal("100000")) -> TradingOrchestrator:
    rm = MagicMock()
    rm._capital_provider = FixedCapitalProvider(equity)
    om = MagicMock()
    om.risk_manager = rm
    return TradingOrchestrator(
        event_bus=MagicMock(),
        order_manager=om,
        strategy_evaluator=MagicMock(),
        feature_fetcher=MagicMock(),
        config=OrchestratorConfig(),
    )


def _sig(**kwargs) -> SignalDTO:
    base = dict(
        symbol="RELIANCE",
        exchange="NSE",
        side="BUY",
        signal_type="BUY",
        confidence=Decimal("0.9"),
        quantity=0,
        entry_price=Decimal("100"),
    )
    base.update(kwargs)
    return SignalDTO(**base)


def test_explicit_quantity_wins():
    orch = _make_orchestrator()
    signal = _sig(quantity=7, position_size_pct=Decimal("50"))
    assert orch._calculate_quantity(signal) == 7


def test_position_size_pct_uses_equity_and_price():
    # equity 100_000, 10% → notional 10_000, price 100 → 100 shares
    orch = _make_orchestrator(Decimal("100000"))
    signal = _sig(position_size_pct=Decimal("10"), entry_price=Decimal("100"))
    assert orch._calculate_quantity(signal) == 100


def test_int_pct_is_not_share_count():
    """Regression: int(2.5) was wrongly used as quantity."""
    orch = _make_orchestrator(Decimal("100000"))
    signal = _sig(position_size_pct=Decimal("2.5"), entry_price=Decimal("250"))
    # 2.5% of 100k = 2500 notional / 250 = 10 shares (not int(2.5)=2)
    assert orch._calculate_quantity(signal) == 10


def test_missing_size_returns_zero():
    orch = _make_orchestrator()
    signal = _sig(position_size_pct=Decimal("0"))
    assert orch._calculate_quantity(signal) == 0
