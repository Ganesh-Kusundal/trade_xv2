"""Position closing for paper trading — stop-loss / take-profit exits and EOD closes.

Extracted from ``analytics.paper.engine.PaperTradingEngine``. Slippage is applied
**once** inside ``OmsBacktestAdapter`` — this module passes the un-slipped price
and records the OMS fill price into the session (F2a/F2d).
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime
from decimal import Decimal

from analytics.oms_fill_price import resolve_oms_fill_price
from analytics.paper.models import (
    OrderSide,
    OrderStatus,
    PaperOrder,
    PaperTrade,
    PositionSide,
)
from domain import Side
from domain.candles.historical import HistoricalBar
from domain.trading_costs import compute_commission

logger = logging.getLogger(__name__)


def _gen_id() -> str:
    return uuid.uuid4().hex[:8]


class PaperPositionCloser:
    """Close paper positions through the OMS for backtest-live parity.

    Parameters
    ----------
    config:
        Paper trading configuration (capital, slippage, commission, etc.).
    oms_adapter:
        Adapter used to close simulated positions. Required.
    record_fill:
        Callback ``record_fill(session, *, order_id, symbol, exchange, side,
        quantity, price, timestamp, trade_tag) -> bool`` supplied by the engine
        to apply a fill to the session's portfolio.
    """

    def __init__(self, config, oms_adapter, record_fill) -> None:
        self._config = config
        self._oms_adapter = oms_adapter
        self._record_fill = record_fill

    def _commission(self, notional: float, side: str) -> float:
        cfg = self._config
        return compute_commission(
            notional,
            side,
            model=cfg.commission_model,
            flat_fee=cfg.commission_flat,
            fees=cfg.indian_market_fees,
        )

    def close(
        self,
        session,
        symbol: str,
        price: float,
        timestamp: datetime,
        reason: str,
    ) -> None:
        """Close a position through OMS for backtest-live parity."""
        view = session._to_paper_position(symbol)
        if view is None:
            return

        # Un-slipped base — OmsBacktestAdapter applies slippage once (F2a).
        dec_price = Decimal(str(price))
        order_id = self._oms_adapter.close_long(
            symbol=symbol,
            exchange="NSE",
            quantity=view.quantity,
            price=dec_price,
            timestamp=timestamp,
            strategy=view.strategy,
            reasons=[reason],
        )

        if order_id is None:
            return

        config = self._config
        if view.side == PositionSide.LONG:
            slip_side = "SELL"
            close_side = Side.SELL
        else:
            slip_side = "BUY"
            close_side = Side.BUY

        exit_price = resolve_oms_fill_price(
            self._oms_adapter,
            order_id,
            base_price=dec_price,
            side=slip_side,
            slippage_pct=config.slippage_pct,
        )

        if view.side == PositionSide.LONG:
            pnl = (exit_price - view.entry_price) * view.quantity
        else:
            pnl = (view.entry_price - exit_price) * view.quantity

        pnl_pct = ((exit_price / view.entry_price) - 1) * 100 if view.entry_price > 0 else 0.0
        if view.side == PositionSide.SHORT:
            pnl_pct = -pnl_pct

        commission = self._commission(exit_price * view.quantity, slip_side)
        slippage_cost = view.quantity * float(dec_price) * (config.slippage_pct / 100)
        net_pnl = pnl - commission
        session.daily_pnl += net_pnl
        session.capital += view.quantity * view.entry_price + net_pnl

        session.trades.append(
            PaperTrade(
                symbol=symbol,
                side=OrderSide.BUY if view.side == PositionSide.LONG else OrderSide.SELL,
                entry_price=view.entry_price,
                exit_price=exit_price,
                quantity=view.quantity,
                entry_time=view.entry_time,
                exit_time=timestamp,
                pnl=net_pnl,
                pnl_pct=pnl_pct,
                commission=commission,
                slippage_cost=slippage_cost,
                strategy=view.strategy,
                reasons=[reason],
            )
        )

        session.orders.append(
            PaperOrder(
                order_id=f"P-{_gen_id()}",
                symbol=symbol,
                side=OrderSide.SELL if view.side == PositionSide.LONG else OrderSide.BUY,
                quantity=view.quantity,
                price=float(dec_price),
                order_time=timestamp,
                status=OrderStatus.FILLED,
                fill_price=exit_price,
                fill_time=timestamp,
                commission=commission,
                slippage=slippage_cost,
                strategy=view.strategy,
                reasons=[reason],
            )
        )

        self._record_fill(
            session,
            order_id=order_id,
            symbol=symbol,
            exchange="NSE",
            side=close_side,
            quantity=view.quantity,
            price=exit_price,
            timestamp=timestamp,
            trade_tag="close",
        )
        session.clear_position(symbol)

    def check_exits(self, session, bar: HistoricalBar) -> None:
        """Check stop-loss and take-profit exits for the bar's symbol."""
        if not session.has_position(bar.symbol):
            return

        view = session._to_paper_position(bar.symbol)
        meta = session.position_meta.get(bar.symbol)
        if view is None:
            return

        stop_loss = meta.stop_loss if meta else view.stop_loss
        take_profit = meta.take_profit if meta else view.take_profit

        if stop_loss is not None and (
            (view.side == PositionSide.LONG and bar.low <= stop_loss)
            or (view.side == PositionSide.SHORT and bar.high >= stop_loss)
        ):
            self.close(session, bar.symbol, stop_loss, bar.timestamp, "Stop-loss hit")
            return

        if take_profit is not None and (
            (view.side == PositionSide.LONG and bar.high >= take_profit)
            or (view.side == PositionSide.SHORT and bar.low <= take_profit)
        ):
            self.close(session, bar.symbol, take_profit, bar.timestamp, "Take-profit hit")
            return
