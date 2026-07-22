"""OMS composition at the runtime layer — single bootstrap surface (Context 6).

Interface ``OmsBootstrap`` delegates here so OMS wiring is not owned by presentation.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any

from application.oms import RiskConfig, RiskManager
from application.oms.capital_provider import resolve_capital_provider
from domain.ports.execution_target import ExecutionTargetKind
from application.oms.factory import create_trading_context
from application.oms.position_manager import PositionManager
from domain.constants import RECONCILIATION_INTERVAL_SECONDS
from domain.constants.defaults import PAPER_INITIAL_CAPITAL

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class OmsCompositionResult:
    trading_context: Any
    risk_manager: RiskManager
    event_log: Any
    execution_ledger: Any


def build_paper_risk_manager(
    *,
    initial_capital: Decimal | None = None,
) -> RiskManager:
    """OMS-owned paper capital (ADR-0012)."""
    capital = initial_capital or Decimal(
        os.getenv("TRADEX_PAPER_CAPITAL", str(PAPER_INITIAL_CAPITAL))
    )
    capital_provider = resolve_capital_provider(
        execution_kind=ExecutionTargetKind.PAPER,
        fixed_capital=capital,
    )
    return RiskManager(
        position_manager=PositionManager(),
        config=RiskConfig(),
        capital_provider=capital_provider,
    )


def compose_trading_context(
    *,
    risk_manager: RiskManager,
    event_bus: Any,
    lifecycle: Any,
    reconciliation_service: Any | None = None,
    reconciliation_interval_seconds: float = RECONCILIATION_INTERVAL_SECONDS,
    events_dir: Path | None = None,
) -> OmsCompositionResult:
    """Build TradingContext + durable stores — canonical OMS bootstrap."""
    from application.oms.daily_pnl_reset_scheduler import DailyPnlResetScheduler
    from infrastructure.bootstrap import (
        build_dead_letter_queue,
        build_execution_ledger,
        build_order_store,
    )
    from infrastructure.event_log import BufferedEventLog
    from infrastructure.event_bus import ProcessedTradeRepository
    from infrastructure.metrics import metrics_registry
    from infrastructure.observability.event_metrics import EventMetrics
    from runtime.ledger_policy import require_execution_ledger, resolve_execution_ledger

    scheduler = DailyPnlResetScheduler(risk_manager=risk_manager)
    try:
        lifecycle.register(scheduler)
    except Exception as exc:  # pragma: no cover
        logger.debug("lifecycle_register_failed: %s", exc)

    event_dir = events_dir or Path("runtime/event-log")
    event_log: Any = None
    try:
        event_log = BufferedEventLog(events_dir=event_dir)
    except Exception as exc:
        logger.error("event_log_build_failed: %s", exc)

    processed_trades: Any = None
    try:
        path = Path("runtime/processed-trades.jsonl")
        path.parent.mkdir(parents=True, exist_ok=True)
        processed_trades = ProcessedTradeRepository.get_instance(persistence_path=path)
    except Exception as exc:
        logger.error("processed_trade_repository_build_failed: %s", exc)

    dead_letter_queue = build_dead_letter_queue()
    order_store = build_order_store()
    execution_ledger = resolve_execution_ledger(builder=build_execution_ledger)
    require_execution_ledger(execution_ledger)

    trading_context = create_trading_context(
        risk_manager=risk_manager,
        reconciliation_service=reconciliation_service,
        reconciliation_interval_seconds=reconciliation_interval_seconds,
        event_log=event_log,
        event_bus=event_bus,
        replay_events=event_log is not None,
        processed_trade_repository=processed_trades,
        dead_letter_queue=dead_letter_queue,
        durable_order_store=order_store,
        execution_ledger=execution_ledger,
        metrics=EventMetrics(),
        metrics_registry=metrics_registry,
    )
    trading_context.attach_lifecycle(lifecycle)

    from application.oms.composition import register_process_oms

    register_process_oms(trading_context)

    return OmsCompositionResult(
        trading_context=trading_context,
        risk_manager=risk_manager,
        event_log=event_log,
        execution_ledger=execution_ledger,
    )
