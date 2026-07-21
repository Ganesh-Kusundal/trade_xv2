"""Position closing for paper trading — thin adapter over the shared engine.

Configures :class:`analytics.simulation.position_closer.PositionCloser` with
paper-specific hooks (REF-5): ``PaperTrade``/``PaperOrder`` records and the
cash-ledger callback. Slippage is applied **once** inside
``OmsBacktestAdapter`` — this module passes the un-slipped price and records
the OMS fill price into the session (F2a/F2d).
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Callable
from datetime import datetime

from analytics.paper.models import (
    OrderStatus,
    PaperOrder,
    PaperSession,
    PaperTrade,
)
from analytics.simulation.position_closer import PositionCloser, PositionCloserHooks
from domain.candles.historical import HistoricalBar
from domain.constants import DEFAULT_EXCHANGE
from domain.enums import PositionSide, Side
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
    on_cash:
        Optional ``(session, delta)`` cash applicator (ledger when wired).
    """

    def __init__(
        self,
        config,
        oms_adapter,
        record_fill,
        on_cash: Callable[[PaperSession, float], None] | None = None,
    ) -> None:
        self._config = config
        self._record_fill = record_fill
        self._on_cash = on_cash
        self._impl = PositionCloser(self._build_hooks(), oms_adapter=oms_adapter)

    def _apply_cash(self, session: PaperSession, delta: float) -> None:
        if self._on_cash is not None:
            self._on_cash(session, delta)
        else:
            session.capital += delta

    def _commission(self, notional: float, side: Side) -> float:
        cfg = self._config
        return compute_commission(
            notional,
            side,
            model=cfg.commission_model,
            flat_fee=cfg.commission_flat,
            fees=cfg.indian_market_fees,
        )

    def _close_side(self, view) -> Side:
        return Side.SELL if view.side == PositionSide.LONG else Side.BUY

    def _book_close_fill(
        self,
        session: PaperSession,
        symbol: str,
        view,
        *,
        exit_price: float,
        requested_price: float,
        timestamp: datetime,
        reason: str,
        order_id: str,
    ) -> None:
        config = self._config
        slip_side = self._close_side(view)
        close_side = Side.SELL if slip_side == Side.SELL else Side.BUY

        if view.side == PositionSide.LONG:
            pnl = (exit_price - view.entry_price) * view.quantity
        else:
            pnl = (view.entry_price - exit_price) * view.quantity

        pnl_pct = ((exit_price / view.entry_price) - 1) * 100 if view.entry_price > 0 else 0.0
        if view.side == PositionSide.SHORT:
            pnl_pct = -pnl_pct

        commission = self._commission(exit_price * view.quantity, slip_side)
        slippage_cost = view.quantity * float(requested_price) * (config.slippage_pct / 100)
        net_pnl = pnl - commission
        session.daily_pnl += net_pnl
        self._apply_cash(session, exit_price * view.quantity - commission)

        session.trades.append(
            PaperTrade(
                symbol=symbol,
                side=Side.BUY if view.side == PositionSide.LONG else Side.SELL,
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
                side=Side.SELL if view.side == PositionSide.LONG else Side.BUY,
                quantity=view.quantity,
                price=float(requested_price),
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
            exchange=DEFAULT_EXCHANGE,
            side=close_side,
            quantity=view.quantity,
            price=exit_price,
            timestamp=timestamp,
            trade_tag="close",
        )

    def _build_hooks(self) -> PositionCloserHooks:
        return PositionCloserHooks(
            position_view=lambda session, symbol: session._to_paper_position(symbol),
            close_side=self._close_side,
            oms_slippage_pct=lambda: self._config.slippage_pct,
            book_close_fill=self._book_close_fill,
        )

    def close(
        self,
        session: PaperSession,
        symbol: str,
        price: float,
        timestamp: datetime,
        reason: str,
    ) -> None:
        """Close a position through OMS for backtest-live parity."""
        self._impl.close(session, symbol, price, timestamp, reason)

    def check_exits(self, session: PaperSession, bar: HistoricalBar) -> None:
        """Check stop-loss and take-profit exits for the bar's symbol."""
        self._impl.check_exits(session, bar)
