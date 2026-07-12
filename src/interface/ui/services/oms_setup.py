"""OMS Setup — constructs Order Management System and Risk services.

Extracted from BrokerService._build_oms_risk_manager() and
_build_and_register_oms_services() to reduce complexity and enable
independent testing.

This module handles:
- RiskManager construction with TrackedCapitalProvider
- TradingContext creation and lifecycle attachment
- DhanReconciliationService setup
- EventLog construction for crash recovery
- DailyPnlResetScheduler registration
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

from application.oms import PositionManager, RiskConfig, RiskManager
from application.oms.capital_provider import GatewayCapitalProvider
from domain.constants import RECONCILIATION_INTERVAL_SECONDS
from domain.constants.defaults import RISK_FALLBACK_CAPITAL
from infrastructure.bootstrap import (
    build_dead_letter_queue,
    build_execution_ledger,
    build_order_store,
)
from interface.ui.services.capital_provider import TrackedCapitalProvider

if TYPE_CHECKING:
    from interface.ui.services.broker_service import BrokerService

logger = logging.getLogger(__name__)


def build_risk_manager(service: BrokerService) -> tuple[RiskManager, GatewayCapitalProvider]:
    """Build RiskManager with tracked capital provider.

    Creates a RiskManager configured with:
    - Real broker balance via GatewayCapitalProvider
    - Fallback tracking via TrackedCapitalProvider
    - Fail-open/fail-closed logic based on RISK_FAIL_OPEN

    The design is fail-safe: no order can be placed against an unknown
    capital baseline unless the operator has explicitly opted into
    fail-open mode.

    Args:
        service: BrokerService instance for fallback tracking

    Returns:
        Tuple of (RiskManager, GatewayCapitalProvider)
    """
    # Create base capital provider. fail_closed=False so soft failures
    # return fallback_balance; TrackedCapitalProvider applies the
    # fail-open / fail-closed policy (0 vs RISK_MANUAL_FAIL_OPEN).
    capital_provider = GatewayCapitalProvider(
        gateway=None,  # Will be updated after gateway construction
        fallback_balance=RISK_FALLBACK_CAPITAL,
        fail_closed=False,
    )

    # Wrap with tracking
    tracked_provider = TrackedCapitalProvider(capital_provider, service)

    # Build risk manager
    risk_manager = RiskManager(
        position_manager=PositionManager(),
        config=RiskConfig(),
        capital_provider=tracked_provider,
    )

    return risk_manager, capital_provider


def _build_reconciliation_service(gateway: Any) -> Any:
    """Build DhanReconciliationService for drift detection.

    Creates a reconciliation service backed by gateway orders and
    portfolio adapters. The OMS's ReconciliationService timer thread
    will call this every 300s. Drift items are surfaced in /metrics
    as reconciliation_drift_count.

    Args:
        gateway: MarketDataGateway instance

    Returns:
        DhanReconciliationService or None if construction fails
    """
    try:
        from interface.ui.services.broker_facade import create_reconciliation_service

        conn = getattr(gateway, "_conn", None)
        if conn is not None:
            from application.oms.recon_heal_policy import log_heal_mode, should_auto_repair

            log_heal_mode()
            reconciliation = create_reconciliation_service(
                orders_adapter=conn.orders,
                portfolio_adapter=conn.portfolio,
                oms=None,  # Set below once OrderManager exists
                auto_repair=should_auto_repair(),
            )
            return reconciliation
    except Exception as exc:
        logger.warning("dhan_reconciliation_build_failed: %s", exc)

    return None


def _build_processed_trade_repository() -> Any:
    """Build durable ProcessedTradeRepository for crash-safe trade dedup."""
    try:
        from infrastructure.event_bus import ProcessedTradeRepository

        path = Path("runtime/processed-trades.jsonl")
        path.parent.mkdir(parents=True, exist_ok=True)
        return ProcessedTradeRepository.get_instance(persistence_path=path)
    except Exception as exc:
        logger.error("processed_trade_repository_build_failed: %s", exc)
        return None


def _build_dead_letter_queue() -> Any:
    """Build the default dead-letter queue for failed event dispatches."""
    try:
        return build_dead_letter_queue()
    except Exception as exc:
        logger.error("dead_letter_queue_build_failed: %s", exc)
        return None


def _build_order_store() -> Any:
    """Build the durable order store (SqliteOrderStore) for crash-safe orders."""
    try:
        return build_order_store()
    except Exception as exc:
        logger.error("order_store_build_failed: %s", exc)
        return None


def _build_execution_ledger() -> Any:
    """Build execution ledger when TRADEX_LEDGER_AUTHORITY=1 (ADR-015)."""
    from runtime.ledger_policy import resolve_execution_ledger

    return resolve_execution_ledger(builder=build_execution_ledger)


def _build_event_log() -> Any:
    """Build BufferedEventLog for crash recovery and OMS replay.

    Creates a BufferedEventLog for crash recovery and OMS replay on startup.
    The TradingContext wires this into the EventBus.

    Returns:
        BufferedEventLog instance or None if construction fails
    """
    try:
        from infrastructure.event_log import BufferedEventLog

        event_log = BufferedEventLog(events_dir=Path("runtime/event-log"))
        return event_log
    except Exception as exc:
        logger.error("event_log_build_failed: %s", exc)
        return None


def register_oms_services(
    service: BrokerService,
    risk_manager: RiskManager,
) -> None:
    """Construct and register OMS services with lifecycle.

    Creates and registers:
    - TradingContext (OrderManager, PositionManager, RiskManager, EventBus)
    - DhanReconciliationService (drift detection)
    - EventLog (crash recovery)

    The TradingContext holds the canonical OrderManager, PositionManager,
    RiskManager, EventBus, and ProcessedTradeRepository. It is the single
    source of truth for order state on the live CLI path.

    Args:
        service: BrokerService instance
        risk_manager: RiskManager instance
    """
    from application.oms import create_trading_context
    from infrastructure.metrics import metrics_registry
    from infrastructure.observability.event_metrics import EventMetrics

    # B-1: Build reconciliation service
    dhan_reconciliation = _build_reconciliation_service(service._gateway)

    # B-2: Build EventLog for crash recovery
    event_log = _build_event_log()
    processed_trades = _build_processed_trade_repository()
    dead_letter_queue = _build_dead_letter_queue()
    order_store = _build_order_store()
    execution_ledger = _build_execution_ledger()

    # Build TradingContext with shared risk_manager, reconciliation, and event_log
    try:
        service._trading_context = create_trading_context(
            risk_manager=risk_manager,
            reconciliation_service=dhan_reconciliation,
            reconciliation_interval_seconds=RECONCILIATION_INTERVAL_SECONDS,
            event_log=event_log,
            event_bus=service._event_bus,
            replay_events=event_log is not None,
            processed_trade_repository=processed_trades,
            dead_letter_queue=dead_letter_queue,
            durable_order_store=order_store,
            execution_ledger=execution_ledger,
            metrics=EventMetrics(),
            metrics_registry=metrics_registry,
        )

        # Attach lifecycle (registers reconciliation service, etc.)
        service._trading_context.attach_lifecycle(service._lifecycle)

        # Point reconciliation at OrderManager so heal mode can upsert when
        # TRADEX_RECONCILIATION_AUTO_REPAIR=1 (default remains report-only).
        if dhan_reconciliation is not None:
            dhan_reconciliation._oms = service._trading_context.order_manager
            # Prefer position_manager for upsert_position during heal
            dhan_reconciliation._oms.position_manager = (
                service._trading_context.position_manager
            )

        # ENG-011: single process OMS book (CLI / API / tradex.connect).
        from application.oms.composition import register_process_oms

        register_process_oms(service._trading_context)

        logger.info("oms_services_registered")

    except Exception as exc:  # pragma: no cover - defensive
        logger.error("trading_context_build_failed: %s", exc)
        service._trading_context = None
