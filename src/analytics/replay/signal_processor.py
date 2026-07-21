"""SignalProcessor — replay adapter over the shared simulation engine (REF-5).

Configures :class:`analytics.simulation.signal_processor.SignalProcessor`
with replay-specific hooks: ``FillRecorder``-backed commission/slippage,
``SimulatedTrade`` records, and equity-based sizing with a capital
affordability loop. Routes through OMS when available for
backtest-live parity; falls back to direct simulation in pure backtest mode.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from decimal import Decimal

from analytics.replay.fill_recorder import FillRecorder
from analytics.replay.models import ReplayConfig, ReplaySession, SimulatedTrade
from analytics.simulation.signal_processor import SignalProcessor as _SharedSignalProcessor
from analytics.simulation.signal_processor import SignalProcessorHooks
from analytics.strategy.models import Signal
from domain.candles.historical import HistoricalBar
from domain.constants import DEFAULT_EXCHANGE
from domain.enums import Side
from domain.orders.sizing import compute_order_quantity
from domain.ports.oms_backtest_adapter import OmsBacktestAdapterPort
from domain.simulation_position_meta import PositionMeta

logger = logging.getLogger(__name__)


class SignalProcessor:
    """Process trade signals into fills for a replay session.

    Parameters
    ----------
    fill_recorder:
        Fills and cost computations are delegated here.
    oms_adapter:
        Optional OMS backtest adapter.  When ``None``, fills are simulated
        directly (pure backtest mode).
    on_sync:
        Optional callback invoked after OMS fills to sync session capital
        from a PortfolioTracker.
    """

    def __init__(
        self,
        fill_recorder: FillRecorder,
        oms_adapter: OmsBacktestAdapterPort | None = None,
        on_sync: Callable[[ReplaySession], None] | None = None,
    ) -> None:
        self._fill_recorder = fill_recorder
        self._config = fill_recorder.config
        self._impl = _SharedSignalProcessor(
            self._build_hooks(), oms_adapter=oms_adapter, on_sync=on_sync
        )

    def _size_with_affordability(self, session: ReplaySession, price: float, equity: float) -> int:
        qty = compute_order_quantity(
            equity=equity, price=price, max_position_pct=self._config.max_position_pct
        )
        while qty > 0:
            notional = price * qty
            commission = self._fill_recorder.compute_commission(notional, Side.BUY)
            if notional + commission <= session.capital:
                break
            qty -= 1
        return qty

    def _book_buy_fill(
        self,
        session: ReplaySession,
        bar: HistoricalBar,
        signal: Signal,
        *,
        price: float,
        base_price: float,
        quantity: int,
        order_id: str,
        via_oms: bool,
    ) -> None:
        notional = price * quantity
        commission = self._fill_recorder.compute_commission(notional, Side.BUY)
        session.capital -= notional + commission
        self._fill_recorder.record(
            session,
            order_id=order_id,
            symbol=bar.symbol,
            exchange=DEFAULT_EXCHANGE,
            side=Side.BUY,
            quantity=quantity,
            price=price,
            timestamp=bar.timestamp,
            trade_tag="open",
        )
        session.mark_symbol(bar.symbol, price)
        session.position_meta[bar.symbol] = PositionMeta(
            entry_time=bar.timestamp,
            stop_loss=signal.stop_loss,
            target=signal.target,
            strategy=signal.strategy,
        )

    def _book_sell_fill(
        self,
        session: ReplaySession,
        bar: HistoricalBar,
        signal: Signal,
        view,
        *,
        price: float,
        base_price: float,
        order_id: str,
        via_oms: bool,
    ) -> None:
        notional = price * view.quantity
        commission = self._fill_recorder.compute_commission(notional, Side.SELL)
        session.capital += notional - commission

        if not via_oms:
            entry_price_d = Decimal(str(view.entry_price))
            exit_price_d = Decimal(str(price))
            commission_d = Decimal(str(commission))
            pnl = (exit_price_d - entry_price_d) * view.quantity - commission_d
            pnl_pct = (
                float(((exit_price_d / entry_price_d) - 1) * 100) if entry_price_d > 0 else 0.0
            )
            session.trades.append(
                SimulatedTrade(
                    symbol=view.symbol,
                    side=view.side,
                    entry_price=view.entry_price,
                    exit_price=price,
                    quantity=view.quantity,
                    entry_time=view.entry_time,
                    exit_time=bar.timestamp,
                    pnl=pnl,
                    pnl_pct=pnl_pct,
                    strategy=view.strategy,
                    reasons=["simulated_signal"],
                )
            )

        self._fill_recorder.record(
            session,
            order_id=order_id,
            symbol=view.symbol,
            exchange=DEFAULT_EXCHANGE,
            side=Side.SELL,
            quantity=view.quantity,
            price=price,
            timestamp=bar.timestamp,
            trade_tag="close",
        )

    def _build_hooks(self) -> SignalProcessorHooks:
        return SignalProcessorHooks(
            equity_for_sizing=lambda session: session.current_equity,
            position_view=lambda session, symbol: session._to_simulated_position(symbol),
            slippage_pct=lambda session, bar: self._fill_recorder.compute_slippage_pct(bar.volume),
            size_for_simulated=self._size_with_affordability,
            size_for_oms=self._size_with_affordability,
            entry_gate=lambda session, config, *, via_oms, symbol: False,
            oms_slippage_pct=lambda config: self._config.slippage_pct,
            buy_order_meta=lambda signal: (signal.strategy, ["replay_signal"]),
            sell_order_meta=lambda signal, view: (signal.strategy, ["replay_signal"]),
            book_buy_fill=self._book_buy_fill,
            book_sell_fill=self._book_sell_fill,
        )

    def process(
        self,
        signal: Signal,
        bar: HistoricalBar,
        session: ReplaySession,
        config: ReplayConfig,
        *,
        fill_price: float | None = None,
    ) -> None:
        """Process a signal for order execution.

        Routes through OMS when available (backtest-live parity).
        Falls back to direct simulation when no OMS adapter is configured
        (pure backtest mode).
        """
        self._impl.process(signal, bar, session, config, fill_price=fill_price)

    def _process_simulated(
        self,
        signal: Signal,
        bar: HistoricalBar,
        session: ReplaySession,
        config: ReplayConfig,
        *,
        fill_price: float | None = None,
    ) -> None:
        """Backward-compat seam used by ReplayEngine's legacy delegation wrappers."""
        self._impl._process_simulated(signal, bar, session, config, fill_price=fill_price)

    def _process_via_oms(
        self,
        signal: Signal,
        bar: HistoricalBar,
        session: ReplaySession,
        config: ReplayConfig,
        *,
        fill_price: float | None = None,
    ) -> None:
        """Backward-compat seam used by ReplayEngine's legacy delegation wrappers."""
        self._impl._process_via_oms(signal, bar, session, config, fill_price=fill_price)
