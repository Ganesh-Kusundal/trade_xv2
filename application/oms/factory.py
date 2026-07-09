"""Factory helpers for creating a TradingContext with optional reconciliation."""

from __future__ import annotations

import logging
from collections.abc import Callable
from decimal import Decimal

from application.oms.context import TradingContext
from application.oms.order_manager import OrderManager
from application.oms.position_manager import PositionManager
from application.oms.protocols import IReconciliationService
from application.oms.risk_manager import RiskConfig, RiskManager
from domain.constants import RECONCILIATION_INTERVAL_SECONDS
from domain.ports import (
    DeadLetterQueuePort,
    EventBusPort,
    EventLogPort,
    OrderStorePort,
    ProcessedTradeRepositoryPort,
)

logger = logging.getLogger(__name__)


def create_trading_context(
    event_log: EventLogPort | None = None,
    reconciliation_service: IReconciliationService | None = None,
    reconciliation_interval_seconds: float = RECONCILIATION_INTERVAL_SECONDS,
    risk_config: RiskConfig | None = None,
    capital_fn: Callable[[], Decimal] | None = None,
    event_bus: EventBusPort | None = None,
    order_manager: OrderManager | None = None,
    position_manager: PositionManager | None = None,
    risk_manager: RiskManager | None = None,
    replay_events: bool = True,
    processed_trade_repository: ProcessedTradeRepositoryPort | None = None,
    dead_letter_queue: DeadLetterQueuePort | None = None,
    durable_order_store: OrderStorePort | None = None,
    enable_durable_orders: bool | None = None,
) -> TradingContext:
    """Create a TradingContext with optional reconciliation.

    This is the recommended entry point for constructing a ``TradingContext``
    when wiring reconciliation into the broker gateway creation flow.

    Args:
        event_log: Persistent event log for replay and audit. Use BufferedEventLog for production.
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
        processed_trade_repository: Durable idempotency ledger for trade events.
    """
    ctx = TradingContext(
        event_log=event_log,
        event_bus=event_bus,
        order_manager=order_manager,
        position_manager=position_manager,
        risk_manager=risk_manager,
        risk_config=risk_config,
        capital_fn=capital_fn,
        replay_events=replay_events,
        reconciliation_service=reconciliation_service,
        reconciliation_interval_seconds=reconciliation_interval_seconds,
        processed_trade_repository=processed_trade_repository,
        dead_letter_queue=dead_letter_queue,
        durable_order_store=durable_order_store,
        enable_durable_orders=enable_durable_orders,
    )
    logger.info(
        "TradingContext created (reconciliation=%s, interval=%ss)",
        reconciliation_service.__class__.__name__ if reconciliation_service else "None",
        reconciliation_interval_seconds,
    )
    return ctx
