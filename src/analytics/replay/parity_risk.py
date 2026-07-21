"""Shared PARITY risk-state feed for replay and paper engines.

Pushes session equity delta into ``RiskManager.update_daily_pnl`` and marks
OMS LTP so daily-loss / loss-CB see the same MTM as the analytics session.
"""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any
from domain.market_enums import ExchangeId

logger = logging.getLogger(__name__)


def feed_parity_risk_state(
    trading_context: Any,
    *,
    current_equity: float,
    open_equity: float,
    bar_symbol: str,
    bar_close: float,
    has_position: bool,
    exchange: str = ExchangeId.NSE,
) -> None:
    """Advance RiskManager daily_pnl from session equity (PARITY only).

    No-op when ``trading_context`` / ``risk_manager`` is missing (PURE_SIM).
    """
    if trading_context is None:
        return
    risk = getattr(trading_context, "risk_manager", None)
    if risk is None:
        return
    if has_position:
        pm = getattr(trading_context, "position_manager", None)
        if pm is not None:
            try:
                pm.update_ltp(bar_symbol, exchange, bar_close)
            except Exception:
                logger.debug("parity_oms_ltp_mark_failed", exc_info=True)
    delta = Decimal(str(current_equity)) - Decimal(str(open_equity))
    try:
        risk.update_daily_pnl(delta)
    except Exception:
        logger.exception("parity_daily_pnl_feed_failed")
