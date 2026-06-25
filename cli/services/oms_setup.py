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
from cli.services.capital_provider import TrackedCapitalProvider
from domain.constants.defaults import RISK_FALLBACK_CAPITAL

if TYPE_CHECKING:
    from cli.services.broker_service import BrokerService

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
    # Create base capital provider
    capital_provider = GatewayCapitalProvider(
        gateway=None,  # Will be updated after gateway construction
        fallback_balance=RISK_FALLBACK_CAPITAL,
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
        from brokers.dhan.reconciliation import create_reconciliation_service

        conn = getattr(gateway, "_conn", None)
        if conn is not None:
            reconciliation = create_reconciliation_service(
                orders_adapter=conn.orders,
                portfolio_adapter=conn.portfolio,
                oms=None,  # Set below once OrderManager exists
                auto_repair=False,
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

    # B-1: Build reconciliation service
    dhan_reconciliation = _build_reconciliation_service(service._gateway)

    # B-2: Build EventLog for crash recovery
    event_log = _build_event_log()
    processed_trades = _build_processed_trade_repository()

    # Build TradingContext with shared risk_manager, reconciliation, and event_log
    try:
        service._trading_context = create_trading_context(
            risk_manager=risk_manager,
            reconciliation_service=dhan_reconciliation,
            reconciliation_interval_seconds=300.0,
            event_log=event_log,
            event_bus=service._event_bus,
            replay_events=event_log is not None,
            processed_trade_repository=processed_trades,
        )

        # Attach lifecycle (registers reconciliation service, etc.)
        service._trading_context.attach_lifecycle(service._lifecycle)

        # Point reconciliation service at OrderManager for auto_repair=False
        # (we only want to surface drift; the operator decides)
        if dhan_reconciliation is not None:
            dhan_reconciliation._oms = service._trading_context.order_manager

        logger.info("oms_services_registered")

    except Exception as exc:  # pragma: no cover - defensive
        logger.error("trading_context_build_failed: %s", exc)
        service._trading_context = None
