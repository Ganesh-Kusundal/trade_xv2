"""Replay/paper fill path — FillReducer then PortfolioProjector."""

from __future__ import annotations

from dataclasses import dataclass, field

from domain.entities import Trade
from domain.fill_reducer import FillReducer
from domain.portfolio_projection import PortfolioProjector


@dataclass
class SimulationFillPipeline:
    """Apply simulated fills through the shared reducer before projection."""

    reducer: FillReducer = field(default_factory=FillReducer)
    projector: PortfolioProjector = field(default_factory=PortfolioProjector)
    _filled_by_order: dict[str, int] = field(default_factory=dict)

    def apply_trade(self, trade: Trade, *, order_quantity: int | None = None) -> bool:
        if trade.quantity <= 0:
            return False
        order_id = trade.order_id or f"sim-{trade.trade_id}"
        oq = order_quantity if order_quantity is not None else trade.quantity
        prior = self._filled_by_order.get(order_id, 0)
        fill = FillReducer.fill_from_trade(
            str(trade.trade_id),
            order_id,
            trade.quantity,
            prior,
            trade.price,
        )
        result = self.reducer.apply(
            fill,
            order_quantity=oq,
            prior_cumulative=prior,
        )
        if not result.accepted:
            return False
        self._filled_by_order[order_id] = prior + trade.quantity
        self.projector.apply_trade(trade)
        return True