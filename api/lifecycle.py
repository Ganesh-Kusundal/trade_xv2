"""Lifecycle management for TradeXV2 API services.

Thin wrapper around TradingRuntimeFactory for backward compatibility.
"""

from __future__ import annotations

import logging

from application.oms.context import TradingContext
from application.oms.risk_manager import RiskConfig
from infrastructure.event_bus import EventBus

logger = logging.getLogger(__name__)


def build_trading_context(
    event_bus: EventBus | None = None,
    capital_fn=None,
    risk_config: RiskConfig | None = None,
    trading_context: TradingContext | None = None,
    **kwargs,
) -> TradingContext:
    """Build or return a TradingContext for the API process.

    When ``trading_context`` is supplied (from TradingRuntimeFactory), returns
    it directly. Otherwise falls back to factory construction with the given
    event_bus (legacy path).
    """
    if trading_context is not None:
        logger.info("Using pre-built TradingContext from runtime factory")
        return trading_context

    from application.oms.factory import create_trading_context

    ctx = create_trading_context(
        event_bus=event_bus,
        risk_config=risk_config,
        capital_fn=capital_fn,
        replay_events=True,
        **kwargs,
    )
    logger.info("TradingContext built for API process (legacy path)")
    return ctx
