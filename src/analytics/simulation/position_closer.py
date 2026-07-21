"""PositionCloser — shared position-exit engine for paper and replay (REF-5).

Both engines close a position the same way: route through OMS when
available (once-only slippage via ``resolve_oms_fill_price``) or book the
given exit price directly otherwise. Trade-record shape, cash/ledger
update, and daily-pnl bookkeeping differ per mode and are supplied via
:class:`PositionCloserHooks`.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any

from analytics.oms_fill_price import resolve_oms_fill_price
from domain.candles.historical import HistoricalBar
from domain.constants import DEFAULT_EXCHANGE
from domain.enums import PositionSide, Side
from domain.ports.oms_backtest_adapter import OmsBacktestAdapterPort

logger = logging.getLogger(__name__)


@dataclass
class PositionCloserHooks:
    """Mode-specific collaborators the shared :class:`PositionCloser` delegates to."""

    position_view: Callable[[Any, str], Any | None]
    close_side: Callable[[Any], Side]
    oms_slippage_pct: Callable[[], float]
    book_close_fill: Callable[..., None]


class PositionCloser:
    """Close a simulated position and record the exit trade.

    Parameters
    ----------
    hooks:
        Mode-specific collaborators (see :class:`PositionCloserHooks`).
    oms_adapter:
        Optional OMS backtest adapter. When ``None``, the given ``price``
        is booked directly (pure backtest / research mode).
    portfolio_tracker:
        Optional portfolio tracker for OMS-backed capital synchronization.
    """

    def __init__(
        self,
        hooks: PositionCloserHooks,
        oms_adapter: OmsBacktestAdapterPort | None = None,
        portfolio_tracker: Any = None,
    ) -> None:
        self._hooks = hooks
        self._oms_adapter = oms_adapter
        self._portfolio_tracker = portfolio_tracker

    @property
    def oms_adapter(self) -> OmsBacktestAdapterPort | None:
        return self._oms_adapter

    def close(
        self,
        session: Any,
        symbol: str,
        price: float,
        timestamp: datetime,
        reason: str,
    ) -> None:
        """Close ``symbol``'s open position at ``price`` and record the trade.

        ``price`` is the un-slipped base (stop/target level or bar close);
        the OMS adapter applies slippage once when present.
        """
        h = self._hooks
        view = h.position_view(session, symbol)
        if view is None:
            return

        dec_price = Decimal(str(price))

        if self._oms_adapter is not None:
            order_id = self._oms_adapter.close_long(
                symbol=symbol,
                exchange=DEFAULT_EXCHANGE,
                quantity=view.quantity,
                price=dec_price,
                timestamp=timestamp,
                strategy=view.strategy,
                reasons=[reason],
            )
            if not order_id:
                return
            exit_price = resolve_oms_fill_price(
                self._oms_adapter,
                order_id,
                base_price=dec_price,
                side=h.close_side(view),
                slippage_pct=h.oms_slippage_pct(),
            )
        else:
            order_id = f"sim-close:{symbol}:{session.bar_count}"
            exit_price = price

        h.book_close_fill(
            session,
            symbol,
            view,
            exit_price=exit_price,
            requested_price=price,
            timestamp=timestamp,
            reason=reason,
            order_id=order_id,
        )
        session.clear_position(symbol)

    def check_exits(self, session: Any, bar: HistoricalBar) -> None:
        """Check stop-loss and take-profit exits for the bar's symbol."""
        h = self._hooks
        if not session.has_position(bar.symbol):
            return

        view = h.position_view(session, bar.symbol)
        meta = session.position_meta.get(bar.symbol)
        if view is None:
            return

        stop_loss = meta.stop_loss if meta else getattr(view, "stop_loss", None)
        take_profit = meta.target if meta else getattr(view, "take_profit", None)

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

    def sync_from_tracker(self, session: Any) -> None:
        """Sync session cash from a PortfolioTracker (OMS-backed capital)."""
        if self._portfolio_tracker is None:
            return
        session.capital = float(self._portfolio_tracker.get_capital())
