"""Lifecycle management for TradeXV2 API services.

Thin wrapper around TradingRuntimeFactory for backward compatibility.
"""

from __future__ import annotations

import logging

from application.oms.context import TradingContext
from application.oms.risk_manager import RiskConfig
from brokers.common.oms.defaults import (
    build_dead_letter_queue,
    build_event_bus,
    build_processed_trade_repository,
)
from infrastructure.event_bus import EventBus

logger = logging.getLogger(__name__)


def build_trading_context(
    event_bus: EventBus | None = None,
    capital_fn=None,
    risk_config: RiskConfig | None = None,
    trading_context: TradingContext | None = None,
    event_log=None,
    dead_letter_queue=None,
    processed_trade_repository=None,
    **kwargs,
) -> TradingContext:
    """Build or return a TradingContext for the API process.

    When ``trading_context`` is supplied (from TradingRuntimeFactory), returns
    it directly. Otherwise falls back to factory construction, filling the
    event-infrastructure defaults (the OMS no longer constructs them itself).
    """
    if trading_context is not None:
        logger.info("Using pre-built TradingContext from runtime factory")
        return trading_context

    if dead_letter_queue is None:
        dead_letter_queue = build_dead_letter_queue()
    if event_bus is None:
        event_bus = build_event_bus(
            event_log=event_log,
            dead_letter_queue=dead_letter_queue,
        )
    if processed_trade_repository is None:
        processed_trade_repository = build_processed_trade_repository()

    from application.oms.factory import create_trading_context

    ctx = create_trading_context(
        event_bus=event_bus,
        risk_config=risk_config,
        capital_fn=capital_fn,
        replay_events=True,
        event_log=event_log,
        dead_letter_queue=dead_letter_queue,
        processed_trade_repository=processed_trade_repository,
        **kwargs,
    )
    logger.info("TradingContext built for API process (legacy path)")
    return ctx
