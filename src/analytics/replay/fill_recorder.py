"""FillRecorder — commission, slippage, and fill recording for replay.

Extracted from ReplayEngine to isolate trading-cost computation and
fill recording into a focused, testable module.

Dependencies (injected via constructor):
    - ReplayConfig (cost model parameters)
    - ReplaySession (fill pipeline target — passed per call)
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from decimal import Decimal

from analytics.replay.models import ReplayConfig, ReplaySession
from domain.entities import Trade
from domain.enums import Side
from domain.trading_costs import (
    compute_commission,
    compute_slippage_pct,
)

logger = logging.getLogger(__name__)


class FillRecorder:
    """Records fills on a ReplaySession and computes trading costs.

    Parameters
    ----------
    config:
        Replay configuration carrying commission/slippage model settings.
    """

    def __init__(self, config: ReplayConfig) -> None:
        self._config = config

    def record(
        self,
        session: ReplaySession,
        *,
        order_id: str,
        symbol: str,
        exchange: str,
        side: Side,
        quantity: int,
        price: float,
        timestamp: datetime | None = None,
        trade_tag: str = "fill",
    ) -> bool:
        """Apply replay fill through FillReducer then PortfolioProjector."""
        if not order_id or quantity <= 0:
            return False
        ts = timestamp or datetime.now(timezone.utc)
        trade = Trade(
            trade_id=f"{order_id}:{trade_tag}",
            order_id=order_id,
            symbol=symbol,
            exchange=exchange,
            side=side,
            quantity=quantity,
            price=Decimal(str(price)),
            trade_value=Decimal(str(price)) * quantity,
            timestamp=ts,
        )
        return session.fill_pipeline.apply_trade(trade, order_quantity=quantity)

    def compute_commission(self, notional: float, side: str) -> float:
        """Compute commission based on the configured model.

        Delegates to domain.trading_costs.compute_commission (single source of truth).
        """
        cfg = self._config
        return compute_commission(
            notional, side,
            model=cfg.commission_model,
            flat_fee=cfg.commission_flat,
            fees=cfg.indian_market_fees,
        )

    def compute_slippage_pct(self, bar_volume: float) -> float:
        """Compute effective slippage percentage based on the configured model.

        Delegates to domain.trading_costs.compute_slippage_pct (single source of truth).
        """
        cfg = self._config
        return compute_slippage_pct(
            cfg.slippage_model,
            cfg.slippage_pct,
            bar_volume,
            cfg.avg_volume,
        )
