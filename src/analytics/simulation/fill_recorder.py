"""FillRecorder — commission, slippage, and fill recording (paper + replay).

Mode-agnostic: only requires ``session.fill_pipeline`` (both ``PaperSession``
and ``ReplaySession`` have it) and a config exposing commission/slippage
model fields. Moved from ``analytics.replay.fill_recorder`` as part of the
REF-5 simulation consolidation.
"""

from __future__ import annotations

import logging
from datetime import datetime
from decimal import Decimal
from typing import Any

from domain.entities import Trade
from domain.enums import Side
from domain.ports.time_service import get_current_clock
from domain.primitives.value_objects import Money, Quantity
from domain.trading_costs import compute_commission, compute_slippage_pct

logger = logging.getLogger(__name__)


class FillRecorder:
    """Records fills on a simulation session and computes trading costs.

    Parameters
    ----------
    config:
        Paper/replay configuration carrying commission/slippage model
        settings (``commission_model``, ``commission_flat``,
        ``indian_market_fees``, and — for volume-weighted slippage —
        ``slippage_model``, ``slippage_pct``, ``avg_volume``).
    """

    def __init__(self, config: Any) -> None:
        self._config = config

    @property
    def config(self) -> Any:
        return self._config

    def record(
        self,
        session: Any,
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
        """Apply a fill through FillReducer then PortfolioProjector."""
        if not order_id or quantity <= 0:
            return False
        ts = timestamp or get_current_clock().now()
        qty = Quantity(Decimal(str(quantity)))
        price_money = Money(Decimal(str(price)))
        trade_value = price_money * qty.magnitude
        trade = Trade(
            trade_id=f"{order_id}:{trade_tag}",
            order_id=order_id,
            symbol=symbol,
            exchange=exchange,
            side=side,
            quantity=qty,
            price=price_money,
            trade_value=trade_value,
            timestamp=ts,
        )
        result: bool = session.fill_pipeline.apply_trade(trade, order_quantity=quantity)
        return result

    def compute_commission(self, notional: float, side: str) -> float:
        """Compute commission based on the configured model.

        Delegates to domain.trading_costs.compute_commission (single source of truth).
        """
        cfg = self._config
        return compute_commission(
            notional,
            side,
            model=cfg.commission_model,
            flat_fee=cfg.commission_flat,
            fees=cfg.indian_market_fees,
        )

    def compute_slippage_pct(self, bar_volume: float) -> float:
        """Compute effective slippage percentage based on the configured model.

        Delegates to domain.trading_costs.compute_slippage_pct (single source of truth).
        Requires the config to expose ``slippage_model`` and ``avg_volume``
        (present on ``ReplayConfig``; ``PaperConfig`` uses a fixed-pct model
        and does not call this method).
        """
        cfg = self._config
        return compute_slippage_pct(
            cfg.slippage_model,
            cfg.slippage_pct,
            bar_volume,
            cfg.avg_volume,
        )
