"""TradingContext factory functions for E2E tests.

Creates fully-wired TradingContext instances with mock brokers
and test-friendly configuration.
"""

from __future__ import annotations
from tests.conftest import build_test_trading_context

from decimal import Decimal
from pathlib import Path

from application.oms.context import TradingContext
from application.oms._internal.risk_manager import RiskConfig, RiskManager
from infrastructure.observability.event_metrics import EventMetrics
from infrastructure.event_bus import EventBus
from infrastructure.event_bus.dead_letter_queue import DeadLetterQueue
from infrastructure.event_log import EventLog


def create_test_trading_context(
    capital: Decimal = Decimal("1000000"),
    risk_config: RiskConfig | None = None,
    events_dir: Path | None = None,
    **kwargs,
) -> TradingContext:
    """Create a TradingContext suitable for E2E testing.

    Parameters
    ----------
    capital : Decimal
        Available capital for risk checks.
    risk_config : RiskConfig | None
        Custom risk configuration.
    events_dir : Path | None
        Directory for event log. If None, no event log is created.
    **kwargs
        Additional arguments passed to TradingContext.

    Returns
    -------
    TradingContext
        Fully wired context with fresh state.
    """
    metrics = EventMetrics()
    dlq = DeadLetterQueue(max_size=1000)
    event_bus = EventBus(metrics=metrics, dead_letter_queue=dlq)

    event_log = None
    if events_dir is not None:
        events_dir.mkdir(parents=True, exist_ok=True)
        event_log = EventLog(events_dir=events_dir)

    position_manager = kwargs.pop("position_manager", None)
    risk_manager = kwargs.pop("risk_manager", None)

    if risk_manager is None:
        from application.oms.position_manager import PositionManager

        if position_manager is None:
            position_manager = PositionManager(
                event_bus=event_bus,
                metrics=metrics,
            )
        risk_manager = RiskManager(
            position_manager=position_manager,
            config=risk_config or RiskConfig(),
            capital_fn=lambda: capital,
        )

    ctx = build_test_trading_context(
        event_bus=event_bus,
        event_log=event_log,
        risk_manager=risk_manager,
        position_manager=position_manager,
        metrics=metrics,
        dead_letter_queue=dlq,
        replay_events=False,  # Disable replay in tests for clean state
        **kwargs,
    )

    return ctx


def create_paper_trading_context(
    capital: Decimal = Decimal("100000"),
    max_position_pct: Decimal = Decimal("25"),
    max_gross_pct: Decimal = Decimal("100"),
    max_daily_loss_pct: Decimal = Decimal("5"),
    **kwargs,
) -> TradingContext:
    """Create a TradingContext with paper-trading-friendly risk limits.

    More permissive than production defaults to allow test flows to proceed.
    """
    risk_config = RiskConfig(
        max_position_pct=max_position_pct,
        max_gross_exposure_pct=max_gross_pct,
        max_daily_loss_pct=max_daily_loss_pct,
        kill_switch=False,
    )
    return create_test_trading_context(
        capital=capital,
        risk_config=risk_config,
        **kwargs,
    )
