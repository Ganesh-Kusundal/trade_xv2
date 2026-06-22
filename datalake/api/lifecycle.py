"""Lifecycle management for TradeXV2 API services.

Constructs TradingContext with OMS components during FastAPI startup.
"""
from __future__ import annotations

import logging
from decimal import Decimal
from pathlib import Path
from typing import Any

from brokers.common.event_bus import EventBus
from brokers.common.event_log import EventLog
from brokers.common.oms.context import TradingContext
from brokers.common.oms.factory import create_trading_context
from brokers.common.oms.risk_manager import RiskConfig

logger = logging.getLogger(__name__)


def build_trading_context(
    event_bus: EventBus | None = None,
    capital_fn=None,
    risk_config: RiskConfig | None = None,
    **kwargs,
) -> TradingContext:
    """Build a TradingContext for the API process.
    
    Parameters
    ----------
    event_bus:
        EventBus instance (created if None).
    capital_fn:
        Callable returning available capital. Defaults to phantom capital.
    risk_config:
        Risk configuration. Uses defaults if None.
    """
    # Initialize EventLog for crash recovery
    event_log = None
    try:
        event_log_path = Path("runtime/event-log")
        event_log_path.mkdir(parents=True, exist_ok=True)
        event_log = EventLog(events_dir=str(event_log_path))
        logger.info("EventLog initialized for crash recovery at %s", event_log_path)
    except Exception as exc:
        logger.warning("EventLog initialization failed (non-fatal): %s", exc)
    
    ctx = create_trading_context(
        event_log=event_log,
        event_bus=event_bus,
        risk_config=risk_config,
        capital_fn=capital_fn or (lambda: Decimal("100000")),  # Default phantom capital
        replay_events=True,
    )
    
    logger.info("TradingContext built for API process")
    return ctx
