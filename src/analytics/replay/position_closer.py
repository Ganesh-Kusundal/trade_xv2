"""PositionCloser — replay adapter over the shared simulation engine (REF-5).

Configures :class:`analytics.simulation.position_closer.PositionCloser` with
replay-specific hooks: ``FillRecorder``-backed commission and
``SimulatedTrade`` records. Exposes ``close``/``close_at_price`` for
end-of-replay closes and stop-loss/target triggers, plus tracker sync for
OMS-backed capital.
"""

from __future__ import annotations

from decimal import Decimal

from analytics.replay.fill_recorder import FillRecorder
from analytics.replay.models import ReplaySession, SimulatedTrade
from analytics.simulation.position_closer import PositionCloser as _SharedPositionCloser
from analytics.simulation.position_closer import PositionCloserHooks
from domain.candles.historical import HistoricalBar
from domain.constants import DEFAULT_EXCHANGE
from domain.enums import Side
from domain.ports.oms_backtest_adapter import OmsBacktestAdapterPort


class PositionCloser:
    """Close positions and record exit trades for a replay session.

    Parameters
    ----------
    fill_recorder:
        Fills and cost computations are delegated here.
    oms_adapter:
        Optional OMS backtest adapter.  When ``None``, closes are simulated.
    portfolio_tracker:
        Optional portfolio tracker for OMS-backed capital synchronization.
    """

    def __init__(
        self,
        fill_recorder: FillRecorder,
        oms_adapter: OmsBacktestAdapterPort | None = None,
        portfolio_tracker=None,
    ) -> None:
        self._fill_recorder = fill_recorder
        self._impl = _SharedPositionCloser(
            self._build_hooks(),
            oms_adapter=oms_adapter,
            portfolio_tracker=portfolio_tracker,
        )

    def _book_close_fill(
        self,
        session: ReplaySession,
        symbol: str,
        view,
        *,
        exit_price: float,
        requested_price: float,
        timestamp,
        reason: str,
        order_id: str,
    ) -> None:
        notional = exit_price * view.quantity
        commission = self._fill_recorder.compute_commission(notional, Side.SELL)
        exit_price_d = Decimal(str(exit_price))
        entry_price_d = Decimal(str(view.entry_price))
        commission_d = Decimal(str(commission))
        pnl = (exit_price_d - entry_price_d) * view.quantity - commission_d
        pnl_pct = float(((exit_price_d / entry_price_d) - 1) * 100) if entry_price_d > 0 else 0.0

        session.capital += notional - commission
        session.trades.append(
            SimulatedTrade(
                symbol=view.symbol,
                side=view.side,
                entry_price=view.entry_price,
                exit_price=exit_price,
                quantity=view.quantity,
                entry_time=view.entry_time,
                exit_time=timestamp,
                pnl=pnl,
                pnl_pct=pnl_pct,
                strategy=view.strategy,
                reasons=[reason],
            )
        )
        self._fill_recorder.record(
            session,
            order_id=order_id,
            symbol=view.symbol,
            exchange=DEFAULT_EXCHANGE,
            side=Side.SELL,
            quantity=view.quantity,
            price=exit_price,
            timestamp=timestamp,
            trade_tag=reason,
        )

    def _build_hooks(self) -> PositionCloserHooks:
        return PositionCloserHooks(
            position_view=lambda session, symbol: session._to_simulated_position(symbol),
            close_side=lambda view: Side.SELL,
            oms_slippage_pct=lambda: self._fill_recorder.config.slippage_pct,
            book_close_fill=self._book_close_fill,
        )

    def close(
        self,
        session: ReplaySession,
        bar: HistoricalBar,
        reason: str,
    ) -> None:
        """Close the symbol's open position and record the trade.

        Routes through OMS when available (backtest-live parity).
        Simulates directly when no OMS adapter is configured.
        """
        if self._impl.oms_adapter is not None:
            price = float(bar.close)
        else:
            slippage_pct = self._fill_recorder.compute_slippage_pct(bar.volume)
            price = float(bar.close) * (1 - slippage_pct / 100)
        self._impl.close(session, bar.symbol, price, bar.timestamp, reason)

    def close_at_price(
        self,
        session: ReplaySession,
        bar: HistoricalBar,
        exit_price: float,
        reason: str,
    ) -> None:
        """Close position at specific price (for stop-loss/target triggers).

        P2-3: This method is called when intra-bar price action hits a
        position's stop-loss or target level.  Routes through OMS when
        available for backtest-live parity; simulates directly otherwise.
        """
        self._impl.close(session, bar.symbol, exit_price, bar.timestamp, reason)

    def sync_from_tracker(self, session: ReplaySession) -> None:
        """Sync session cash from PortfolioTracker (OMS-backed capital)."""
        self._impl.sync_from_tracker(session)
