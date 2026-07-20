"""SignalProcessor — signal routing and fill simulation for replay.

Extracted from ReplayEngine to isolate signal → fill logic into a
focused, testable module.  Routes through OMS when available for
backtest-live parity; falls back to direct simulation in pure backtest mode.

Dependencies (injected via constructor):
    - FillRecorder (commission, slippage, fill recording)
    - OmsBacktestAdapterPort | None (OMS adapter — None for pure-simulate)
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from decimal import Decimal

from analytics.oms_fill_price import resolve_oms_fill_price
from analytics.replay.fill_recorder import FillRecorder
from analytics.replay.models import ReplayConfig, ReplaySession, SimulatedTrade
from analytics.strategy.models import Signal
from domain.candles.historical import HistoricalBar
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
        self._oms_adapter = oms_adapter
        self._on_sync = on_sync

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

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
        if not signal.is_actionable:
            return

        if self._oms_adapter is not None:
            self._process_via_oms(signal, bar, session, config, fill_price=fill_price)
        else:
            self._process_simulated(signal, bar, session, config, fill_price=fill_price)

    # ------------------------------------------------------------------
    # Pure-simulate path
    # ------------------------------------------------------------------

    def _process_simulated(
        self,
        signal: Signal,
        bar: HistoricalBar,
        session: ReplaySession,
        config: ReplayConfig,
        *,
        fill_price: float | None = None,
    ) -> None:
        """Simulate fills directly without OMS routing (pure backtest mode).

        Used when no trading_context or oms_adapter is provided.
        """
        base_price = float(fill_price if fill_price is not None else bar.close)

        if signal.is_buy and not session.has_position(bar.symbol):
            slippage_pct = self._fill_recorder.compute_slippage_pct(bar.volume)
            price = base_price * (1 + slippage_pct / 100)
            qty = compute_order_quantity(
                equity=session.current_equity,
                price=price,
                max_position_pct=config.max_position_pct,
            )
            while qty > 0:
                notional = price * qty
                commission = self._fill_recorder.compute_commission(notional, "BUY")
                cost = notional + commission
                if cost <= session.capital:
                    break
                qty -= 1
            if qty > 0:
                notional = price * qty
                commission = self._fill_recorder.compute_commission(notional, "BUY")
                cost = notional + commission
                session.capital -= cost
                order_id = f"sim-open:{bar.symbol}:{session.bar_count}"
                self._fill_recorder.record(
                    session,
                    order_id=order_id,
                    symbol=bar.symbol,
                    exchange="NSE",
                    side=Side.BUY,
                    quantity=qty,
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

        elif signal.is_sell and session.has_position(bar.symbol):
            view = session._to_simulated_position(bar.symbol)
            if view is None:
                return
            slippage_pct = self._fill_recorder.compute_slippage_pct(bar.volume)
            price = base_price * (1 - slippage_pct / 100)
            notional = price * view.quantity
            commission = self._fill_recorder.compute_commission(notional, "SELL")
            proceeds = notional - commission
            session.capital += proceeds

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
            order_id = f"sim-close:{view.symbol}:{session.bar_count}"
            self._fill_recorder.record(
                session,
                order_id=order_id,
                symbol=view.symbol,
                exchange="NSE",
                side=Side.SELL,
                quantity=view.quantity,
                price=price,
                timestamp=bar.timestamp,
                trade_tag="close",
            )
            session.clear_position(view.symbol)

    # ------------------------------------------------------------------
    # OMS-backed path
    # ------------------------------------------------------------------

    def _process_via_oms(
        self,
        signal: Signal,
        bar: HistoricalBar,
        session: ReplaySession,
        config: ReplayConfig,
        *,
        fill_price: float | None = None,
    ) -> None:
        """Route signal through OMS for backtest-live parity (P0-2).

        Opens/closes positions via :class:`OmsBacktestAdapter`, which consults
        the same risk gates, idempotency ledger, and event bus as live trading.
        """
        if signal.is_buy and not session.has_position(bar.symbol):
            base_price = fill_price if fill_price is not None else bar.close
            price = Decimal(str(base_price))
            qty = compute_order_quantity(
                equity=session.current_equity,
                price=float(price),
                max_position_pct=config.max_position_pct,
            )
            while qty > 0:
                notional = float(price) * qty
                commission = self._fill_recorder.compute_commission(notional, "BUY")
                cost = notional + commission
                if cost <= session.capital:
                    break
                qty -= 1

            if qty > 0:
                order_id = self._oms_adapter.open_long(
                    symbol=bar.symbol,
                    exchange="NSE",
                    quantity=qty,
                    price=price,
                    timestamp=bar.timestamp,
                    strategy=signal.strategy,
                    reasons=["replay_signal"],
                )
                if order_id:
                    # Session must book the OMS fill (slipped once), not base_price (F2d).
                    fill_px = resolve_oms_fill_price(
                        self._oms_adapter,
                        order_id,
                        base_price=price,
                        side="BUY",
                        slippage_pct=config.slippage_pct,
                    )
                    notional = fill_px * qty
                    commission = self._fill_recorder.compute_commission(notional, "BUY")
                    cost = notional + commission
                    session.capital -= cost
                    self._fill_recorder.record(
                        session,
                        order_id=order_id,
                        symbol=bar.symbol,
                        exchange="NSE",
                        side=Side.BUY,
                        quantity=qty,
                        price=fill_px,
                        timestamp=bar.timestamp,
                        trade_tag="open",
                    )
                    session.mark_symbol(bar.symbol, fill_px)
                    session.position_meta[bar.symbol] = PositionMeta(
                        entry_time=bar.timestamp,
                        stop_loss=signal.stop_loss,
                        target=signal.target,
                        strategy=signal.strategy,
                    )
                    if self._on_sync is not None:
                        self._on_sync(session)

        elif signal.is_sell and session.has_position(bar.symbol):
            view = session._to_simulated_position(bar.symbol)
            if view is None:
                return
            base_price = fill_price if fill_price is not None else bar.close
            price = Decimal(str(base_price))
            order_id = self._oms_adapter.close_long(
                symbol=bar.symbol,
                exchange="NSE",
                quantity=view.quantity,
                price=price,
                timestamp=bar.timestamp,
                strategy=signal.strategy,
                reasons=["replay_signal"],
            )
            if order_id:
                fill_px = resolve_oms_fill_price(
                    self._oms_adapter,
                    order_id,
                    base_price=price,
                    side="SELL",
                    slippage_pct=config.slippage_pct,
                )
                notional = fill_px * view.quantity
                commission = self._fill_recorder.compute_commission(notional, "SELL")
                proceeds = notional - commission
                session.capital += proceeds
                self._fill_recorder.record(
                    session,
                    order_id=order_id,
                    symbol=bar.symbol,
                    exchange="NSE",
                    side=Side.SELL,
                    quantity=view.quantity,
                    price=fill_px,
                    timestamp=bar.timestamp,
                    trade_tag="close",
                )
                session.clear_position(bar.symbol)
                if self._on_sync is not None:
                    self._on_sync(session)
