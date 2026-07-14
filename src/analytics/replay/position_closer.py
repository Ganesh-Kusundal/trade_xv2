"""PositionCloser — position closing and trade recording for replay.

Extracted from ReplayEngine to isolate exit logic (end-of-replay closes,
stop-loss/target triggers, tracker sync) into a focused, testable module.

Dependencies (injected via constructor):
    - FillRecorder (commission, slippage, fill recording)
    - OmsBacktestAdapterPort | None (OMS adapter — None for pure-simulate)
    - portfolio_tracker | None (for OMS-backed capital sync)
"""

from __future__ import annotations

import logging
from decimal import Decimal

from analytics.oms_fill_price import resolve_oms_fill_price
from analytics.replay.fill_recorder import FillRecorder
from analytics.replay.models import ReplayConfig, ReplaySession, SimulatedTrade
from domain.candles.historical import HistoricalBar
from domain.enums import Side
from domain.ports.oms_backtest_adapter import OmsBacktestAdapterPort

logger = logging.getLogger(__name__)


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
        self._oms_adapter = oms_adapter
        self._portfolio_tracker = portfolio_tracker

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

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
        view = session._to_simulated_position(bar.symbol)
        if view is None:
            return

        # Pure-sim applies slippage here; OMS path passes un-slipped base (adapter slips once).
        if self._oms_adapter is not None:
            price = Decimal(str(float(bar.close)))
            order_id = self._oms_adapter.close_long(
                symbol=view.symbol,
                exchange="NSE",
                quantity=view.quantity,
                price=price,
                timestamp=bar.timestamp,
                strategy=view.strategy,
                reasons=[reason],
            )
            if order_id is None:
                return
            exit_price = resolve_oms_fill_price(
                self._oms_adapter,
                order_id,
                base_price=price,
                side="SELL",
                slippage_pct=self._fill_recorder._config.slippage_pct,
            )
        else:
            slippage_pct = self._fill_recorder.compute_slippage_pct(bar.volume)
            exit_price = float(bar.close) * (1 - slippage_pct / 100)
            order_id = f"sim-close:{view.symbol}:{session.bar_count}"

        notional = exit_price * view.quantity
        commission = self._fill_recorder.compute_commission(notional, "SELL")
        exit_price_d = Decimal(str(exit_price))
        entry_price_d = Decimal(str(view.entry_price))
        commission_d = Decimal(str(commission))
        pnl = (exit_price_d - entry_price_d) * view.quantity - commission_d
        pnl_pct = (
            float(((exit_price_d / entry_price_d) - 1) * 100)
            if entry_price_d > 0
            else 0.0
        )

        session.capital += notional - commission
        session.trades.append(
            SimulatedTrade(
                symbol=view.symbol,
                side=view.side,
                entry_price=view.entry_price,
                exit_price=exit_price,
                quantity=view.quantity,
                entry_time=view.entry_time,
                exit_time=bar.timestamp,
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
            exchange="NSE",
            side=Side.SELL,
            quantity=view.quantity,
            price=exit_price,
            timestamp=bar.timestamp,
            trade_tag=reason,
        )
        session.clear_position(view.symbol)

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

        Parameters
        ----------
        session:
            Current replay session state.
        bar:
            The bar where stop/target was hit.
        exit_price:
            The price at which to exit (stop_loss or target level).
        reason:
            Human-readable reason for the exit (e.g., "Stop-loss hit").
        """
        view = session._to_simulated_position(bar.symbol)
        if view is None:
            return

        # Un-slipped stop/target — OMS adapter applies slippage once when present.
        price = Decimal(str(exit_price))

        if self._oms_adapter is not None:
            order_id = self._oms_adapter.close_long(
                symbol=view.symbol,
                exchange="NSE",
                quantity=view.quantity,
                price=price,
                timestamp=bar.timestamp,
                strategy=view.strategy,
                reasons=[reason],
            )
            if order_id is None:
                return
            booked = resolve_oms_fill_price(
                self._oms_adapter,
                order_id,
                base_price=price,
                side="SELL",
                slippage_pct=self._fill_recorder._config.slippage_pct,
            )
        else:
            order_id = f"sim-close:{view.symbol}:{session.bar_count}"
            booked = exit_price

        notional = booked * view.quantity
        commission = self._fill_recorder.compute_commission(notional, "SELL")
        exit_price_d = Decimal(str(booked))
        entry_price_d = Decimal(str(view.entry_price))
        commission_d = Decimal(str(commission))
        pnl = (exit_price_d - entry_price_d) * view.quantity - commission_d
        pnl_pct = (
            float(((exit_price_d / entry_price_d) - 1) * 100)
            if entry_price_d > 0
            else 0.0
        )

        session.capital += notional - commission
        session.trades.append(
            SimulatedTrade(
                symbol=view.symbol,
                side=view.side,
                entry_price=view.entry_price,
                exit_price=booked,
                quantity=view.quantity,
                entry_time=view.entry_time,
                exit_time=bar.timestamp,
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
            exchange="NSE",
            side=Side.SELL,
            quantity=view.quantity,
            price=booked,
            timestamp=bar.timestamp,
            trade_tag=reason,
        )
        session.clear_position(view.symbol)

    def sync_from_tracker(self, session: ReplaySession) -> None:
        """Sync session cash from PortfolioTracker (OMS-backed capital)."""
        if self._portfolio_tracker is None:
            return
        session.capital = float(self._portfolio_tracker.get_capital())
