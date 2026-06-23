"""Factory helpers for creating a TradingContext with optional reconciliation."""

from __future__ import annotations

import logging
from collections.abc import Callable
from decimal import Decimal
from typing import Any

from domain.constants import RECONCILIATION_INTERVAL_SECONDS
from infrastructure.event_bus import EventBus
from infrastructure.event_bus.async_event_bus import AsyncEventBus
from brokers.common.event_log import EventLog
from brokers.common.oms.context import TradingContext
from brokers.common.oms.order_manager import OrderManager
from brokers.common.oms.position_manager import PositionManager
from brokers.common.oms.risk_manager import RiskConfig, RiskManager

logger = logging.getLogger(__name__)


def create_trading_context(
    event_log: EventLog | None = None,
    reconciliation_service: Any = None,
    reconciliation_interval_seconds: float = RECONCILIATION_INTERVAL_SECONDS,
    risk_config: RiskConfig | None = None,
    capital_fn: Callable[[], Decimal] | None = None,
    event_bus: EventBus | AsyncEventBus | None = None,
    order_manager: OrderManager | None = None,
    position_manager: PositionManager | None = None,
    risk_manager: RiskManager | None = None,
    replay_events: bool = True,
) -> TradingContext:
    """Create a TradingContext with optional reconciliation.

    This is the recommended entry point for constructing a ``TradingContext``
    when wiring reconciliation into the broker gateway creation flow.

    Args:
        event_log: Persistent event log for replay and audit.
        reconciliation_service: Broker-specific reconciliation service that
            exposes a ``reconcile(local_orders, local_positions)`` method.
            When provided, periodic reconciliation starts automatically.
        reconciliation_interval_seconds: Seconds between reconciliation runs.
        risk_config: Custom risk configuration.
        capital_fn: Callable returning current available capital.
        event_bus: Pre-existing EventBus (created if *None*).
        order_manager: Pre-existing OrderManager.
        position_manager: Pre-existing PositionManager.
        risk_manager: Pre-existing RiskManager.
        replay_events: Whether to replay the event log into the OMS on boot.
    """
    ctx = TradingContext(
        event_log=event_log,
        event_bus=event_bus if isinstance(event_bus, EventBus) and not isinstance(event_bus, AsyncEventBus) else None,
        async_bus=event_bus if isinstance(event_bus, AsyncEventBus) else None,
        order_manager=order_manager,
        position_manager=position_manager,
        risk_manager=risk_manager,
        risk_config=risk_config,
        capital_fn=capital_fn,
        replay_events=replay_events,
        reconciliation_service=reconciliation_service,
        reconciliation_interval_seconds=reconciliation_interval_seconds,
    )
    logger.info(
        "TradingContext created (reconciliation=%s, interval=%ss)",
        reconciliation_service.__class__.__name__ if reconciliation_service else "None",
        reconciliation_interval_seconds,
    )
    return ctx
