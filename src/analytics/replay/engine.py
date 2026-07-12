"""ReplayEngine — bar-by-bar historical replay through FeaturePipeline + StrategyPipeline.

The engine processes OHLCV data one bar at a time, running the same
FeaturePipeline and StrategyPipeline used in live trading. This ensures
complete parity: if a strategy works in replay, it will work in live.

P0-2 OMS Integration: All order execution is routed through
:class:`OmsBacktestAdapter`, ensuring backtest-live parity for risk gates,
idempotency, and event publishing.

P2-3 Intra-Bar Checks: The engine checks open positions against stop-loss and
target levels on every bar using intra-bar high/low, not just on explicit
signals. This prevents unrealistic fills and improves backtest fidelity.

P5.2 Window Optimization: Implements lazy loading and bounded memory access.
The engine now uses a circular buffer for the replay window instead of
accumulating all bars in a list, ensuring O(window_size) memory regardless
of dataset size.

Flow per bar:
    1. Receive bar (OHLCV)
    2. Append to sliding window (bounded by window_size)
    3. Run FeaturePipeline on the window
    4. Construct Candidate from latest bar
    5. Run StrategyPipeline.evaluate_single(candidate, features)
    6. P2-3: Check intra-bar stop-loss/target for open positions
    7. Process Signals via OMS adapter
    8. Update equity curve

Usage:
    from analytics.pipeline import FeaturePipeline, RSI, ATR, SMA
    from analytics.strategy import StrategyPipeline, MomentumStrategy

    pipeline = FeaturePipeline().add(RSI(14)).add(ATR(14)).add(SMA(20))
    strategy = StrategyPipeline(strategies=[MomentumStrategy()])

    # Requires trading_context or oms_adapter for order execution
    from interface.ui.services.compose import build_runtime
    runtime = build_runtime("dhan")
    engine = ReplayEngine(
        pipeline, strategy, trading_context=runtime.trading_context
    )
    result = engine.run(dataframe)
"""

from __future__ import annotations

import logging
from collections import deque
from datetime import datetime, timezone
from decimal import Decimal

import numpy as np
import pandas as pd

from analytics.pipeline.errors import FeaturePipelineError
from analytics.pipeline.pipeline import FeaturePipeline
from analytics.replay.fill_recorder import FillRecorder
from analytics.replay.models import (
    FillModel,
    ReplayConfig,
    ReplayResult,
    ReplaySession,
    SimulatedTrade,
)
from analytics.replay.position_closer import PositionCloser
from analytics.replay.signal_processor import SignalProcessor
from domain.candles.historical import HistoricalBar
from analytics.scanner.models import Candidate
from analytics.strategy.models import Signal
from analytics.strategy.pipeline import StrategyPipeline
from domain.analytics.statistics import StatisticsEngine
from domain.entities import Trade
from domain.enums import Side
from domain.orders.sizing import compute_order_quantity
from domain.ports.oms_backtest_adapter import OmsBacktestAdapterPort
from domain.runtime_hooks import create_oms_backtest_adapter
from domain.simulation_position_meta import PositionMeta
from domain.trading_costs import (
    compute_commission,
    compute_slippage_pct,
)

logger = logging.getLogger(__name__)


class ReplayEngine:
    """Bar-by-bar historical replay engine.

    Processes OHLCV data through the same FeaturePipeline + StrategyPipeline
    used in live trading, ensuring complete parity.

    P0-2: All order execution is routed through :class:`OmsBacktestAdapter`
    for backtest-live parity. A ``trading_context`` (or direct ``oms_adapter``)
    is required.

    P2-3: Open positions are checked against stop-loss and target levels on
    every bar using intra-bar high/low data.

    P5.2: Uses bounded deque for window storage instead of unbounded list,
    ensuring O(window_size) memory regardless of input dataset size.

    Parameters
    ----------
    pipeline:
        FeaturePipeline for computing indicators on each window.
    strategy_pipeline:
        StrategyPipeline for evaluating candidates on each bar.
    config:
        Replay configuration (capital, slippage, warmup, etc.).
    event_bus:
        Optional EventBus for publishing signals.
    trading_context:
        OMS TradingContext. Required unless ``oms_adapter`` is provided directly.
    oms_adapter:
        Pre-built OMS backtest adapter. Takes precedence over ``trading_context``.
    """

    def __init__(
        self,
        pipeline: FeaturePipeline | None = None,
        strategy_pipeline: StrategyPipeline | None = None,
        config: ReplayConfig | None = None,
        event_bus=None,
        trading_context=None,
        execution_adapter: object | None = None,
        oms_adapter: OmsBacktestAdapterPort | None = None,
        portfolio_tracker=None,
        event_schedule: dict[pd.Timestamp, list] | None = None,
        allow_simulate_without_oms: bool = False,
    ) -> None:
        self._pipeline = pipeline or FeaturePipeline()
        self._strategy = strategy_pipeline or StrategyPipeline()
        self._config = config or ReplayConfig()
        self._event_bus = event_bus
        self._trading_context = trading_context
        self._execution_adapter = execution_adapter
        self._portfolio_tracker = portfolio_tracker
        # P0-1 fix: Event schedule maps timestamps to lists of DomainEvents
        # that should be published BEFORE processing the bar at that timestamp.
        # This ensures events and bars are interleaved in time order, not
        # all events published before all bars are processed.
        self._event_schedule = event_schedule or {}

        if oms_adapter is not None:
            self._oms_adapter = oms_adapter
        elif trading_context is not None:
            cfg = self._config
            self._oms_adapter = create_oms_backtest_adapter(
                trading_context,
                mode="replay",
                slippage_pct=cfg.slippage_pct,
                commission_flat=cfg.commission_flat,
                execution_adapter=execution_adapter,
            )
        elif allow_simulate_without_oms:
            # Pure backtest mode: no OMS routing, fills are simulated directly.
            # This allows BacktestEngine and WalkForwardEngine to work standalone
            # without requiring a TradingContext composition root.
            self._oms_adapter = None
            logger.debug(
                "ReplayEngine running in pure-simulate mode (no OMS adapter). "
                "Fills will be simulated without risk gates."
            )
        else:
            raise TypeError(
                "ReplayEngine requires trading_context (or oms_adapter) for order execution. "
                "Pass allow_simulate_without_oms=True for pure backtest mode without OMS."
            )

        # Sub-modules extracted for focused responsibility.
        self._fill_recorder = FillRecorder(self._config)
        self._position_closer = PositionCloser(
            self._fill_recorder, self._oms_adapter, self._portfolio_tracker,
        )
        self._signal_processor = SignalProcessor(
            self._fill_recorder,
            self._oms_adapter,
            on_sync=self._position_closer.sync_from_tracker,
        )

    # ------------------------------------------------------------------
    # Delegation wrappers (backward-compatible private methods)
    # ------------------------------------------------------------------

    def _record_session_fill(
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
        return self._fill_recorder.record(
            session,
            order_id=order_id,
            symbol=symbol,
            exchange=exchange,
            side=side,
            quantity=quantity,
            price=price,
            timestamp=timestamp,
            trade_tag=trade_tag,
        )

    def _compute_commission(self, notional: float, side: str) -> float:
        """Compute commission based on the configured model."""
        return self._fill_recorder.compute_commission(notional, side)

    def _compute_slippage_pct(self, bar_volume: float) -> float:
        """Compute effective slippage percentage based on the configured model."""
        return self._fill_recorder.compute_slippage_pct(bar_volume)

    def _process_signal(
        self,
        signal: Signal,
        bar: HistoricalBar,
        session: ReplaySession,
        config: ReplayConfig,
        fill_price: float | None = None,
    ) -> None:
        """Process a signal for order execution."""
        self._signal_processor.process(
            signal, bar, session, config, fill_price=fill_price,
        )

    def _process_signal_simulated(
        self,
        signal: Signal,
        bar: HistoricalBar,
        session: ReplaySession,
        config: ReplayConfig,
        fill_price: float | None = None,
    ) -> None:
        """Simulate fills directly without OMS routing (pure backtest mode)."""
        self._signal_processor._process_simulated(
            signal, bar, session, config, fill_price=fill_price,
        )

    def _process_signal_via_oms(
        self,
        signal: Signal,
        bar: HistoricalBar,
        session: ReplaySession,
        config: ReplayConfig,
        fill_price: float | None = None,
    ) -> None:
        """Route signal through OMS for backtest-live parity (P0-2)."""
        self._signal_processor._process_via_oms(
            signal, bar, session, config, fill_price=fill_price,
        )

    def _close_position(
        self, session: ReplaySession, bar: HistoricalBar, reason: str,
    ) -> None:
        """Close the symbol's open position and record the trade."""
        self._position_closer.close(session, bar, reason)

    def _close_position_at_price(
        self,
        session: ReplaySession,
        bar: HistoricalBar,
        exit_price: float,
        reason: str,
    ) -> None:
        """Close position at specific price (for stop-loss/target triggers)."""
        self._position_closer.close_at_price(session, bar, exit_price, reason)

    def _sync_session_from_tracker(self, session: ReplaySession) -> None:
        """Sync session cash from PortfolioTracker (OMS-backed capital)."""
        self._position_closer.sync_from_tracker(session)

    # ------------------------------------------------------------------
    # Feature pipeline
    # ------------------------------------------------------------------

    def _run_features(
        self,
        window_df: pd.DataFrame,
        session: ReplaySession,
        config: ReplayConfig,
    ) -> pd.DataFrame | None:
        """Run feature pipeline; return None on fail-closed skip (no neutral fallback)."""
        self._pipeline.fail_closed = config.fail_closed_features
        try:
            return self._pipeline.run(window_df)
        except FeaturePipelineError as exc:
            logger.warning(
                "Feature pipeline fail-closed at bar %d: %s",
                session.bar_count,
                exc,
            )
            return None

    # ------------------------------------------------------------------
    # Main run entry points
    # ------------------------------------------------------------------

    def run(self, data: pd.DataFrame, *, symbol: str = "SYMBOL") -> ReplayResult:
        """Run replay on OHLCV DataFrame.

        Parameters
        ----------
        data:
            DataFrame with columns: timestamp/date, open, high, low, close, volume.
            If multiple symbols, must have a 'symbol' column.
        symbol:
            Symbol name if data doesn't have a 'symbol' column.

        Returns
        -------
        ReplayResult with all signals, trades, equity curve, and metrics.
        """
        if data.empty:
            return ReplayResult(config=self._config)

        # P5.2: Avoid full DataFrame copy — work with view where possible
        df = data
        ts_col = (
            "timestamp" if "timestamp" in df.columns else "date" if "date" in df.columns else None
        )
        if ts_col is None:
            raise ValueError("Data must have a 'timestamp' or 'date' column")

        # Only copy if we need to mutate timestamp column
        if not pd.api.types.is_datetime64_any_dtype(df[ts_col]):
            df = df.copy()
            df[ts_col] = pd.to_datetime(df[ts_col])
        else:
            df = df.copy()  # Sort requires copy for index reset

        df = df.sort_values(ts_col).reset_index(drop=True)

        # If multi-symbol, group and process each
        if "symbol" in df.columns:
            return self._run_multi_symbol(df, ts_col)

        return self._run_single(df, symbol, ts_col)

    def compute_statistics(
        self,
        session: ReplaySession,
        *,
        benchmark: pd.DataFrame | None = None,
        annualization_factor: int = 252,
        risk_free_rate: float = 0.065,
    ) -> dict:
        """Compute performance metrics for a replay session via the StatisticsEngine.

        This is the same pure math used by the BacktestEngine, so replay
        results can be inspected directly (trade analysis, Sharpe, drawdown,
        benchmark comparison) without running a full backtest. It does not
        mutate the session or change ``ReplayResult``.
        """
        initial = session.equity_curve[0][1] if session.equity_curve else 0.0
        final = session.current_equity
        return StatisticsEngine.compute(
            session.equity_curve,
            session.trades,
            initial=initial,
            final=final,
            annualization_factor=annualization_factor,
            risk_free_rate=risk_free_rate,
            benchmark=benchmark,
        )

    # ------------------------------------------------------------------
    # Single-symbol replay
    # ------------------------------------------------------------------

    def _run_single(self, df: pd.DataFrame, symbol: str, ts_col: str) -> ReplayResult:
        """Process a single symbol's data bar-by-bar."""
        config = self._config
        session = ReplaySession(capital=config.initial_capital)
        session.peak_equity = config.initial_capital
        session.equity_curve.append((df[ts_col].iloc[0], config.initial_capital))

        # Pre-allocated numpy arrays as circular buffer (ring buffer).
        # pd.DataFrame(dict_of_arrays) is 10-20x faster than pd.DataFrame(list_of_dicts)
        # because numpy arrays are columnar and don't require per-row dict unpacking.
        # P5.2: Circular buffer uses modular indexing instead of O(n) shift-left per bar,
        # eliminating the numpy memmove entirely. Write pointer advances with modulo
        # arithmetic, and the window is reconstructed in chronological order only when
        # building the DataFrame for the FeaturePipeline.
        window_size = config.window_size if config.window_size > 0 else 0
        if window_size > 0:
            # Pre-allocate numpy arrays for each column (contiguous memory)
            _arr_open = np.empty(window_size, dtype=np.float64)
            _arr_high = np.empty(window_size, dtype=np.float64)
            _arr_low = np.empty(window_size, dtype=np.float64)
            _arr_close = np.empty(window_size, dtype=np.float64)
            _arr_volume = np.empty(window_size, dtype=np.float64)
            _arr_symbol = np.empty(window_size, dtype=object)
            _arr_timestamp = np.empty(window_size, dtype="datetime64[ns]")
            _filled = 0
            _head = 0  # circular buffer write pointer
        else:
            # Unlimited window — fall back to deque (no pre-allocation possible)
            _window_data = deque()

        warmup_done = False
        pending_signals: list[tuple[Signal, HistoricalBar]] = []

        for idx in range(len(df)):
            row = df.iloc[idx]
            bar_ts = row[ts_col]

            bar = HistoricalBar.from_replay(
                symbol=symbol,
                timestamp=bar_ts,
                open=float(row.get("open", 0)),
                high=float(row.get("high", 0)),
                low=float(row.get("low", 0)),
                close=float(row.get("close", 0)),
                volume=float(row.get("volume", 0)),
            )

            # P0-1 fix: Publish scheduled events BEFORE processing this bar.
            # Events are interleaved by timestamp to ensure deterministic replay
            # that matches the original event/bar time ordering.
            if self._event_schedule and self._event_bus is not None:
                self._publish_scheduled_events(bar_ts)

            # Process pending signals from previous bar using this bar's open
            if pending_signals:
                for sig, _sig_bar in pending_signals:
                    self._process_signal(sig, bar, session, config, fill_price=bar.open)
                    if config.publish_events and self._event_bus is not None:
                        self._publish_signal(sig)
                pending_signals.clear()

            # Write bar into circular buffer (O(1) per bar — no memmove)
            if window_size > 0:
                _widx = _head
                _arr_open[_widx] = bar.open
                _arr_high[_widx] = bar.high
                _arr_low[_widx] = bar.low
                _arr_close[_widx] = bar.close
                _arr_volume[_widx] = bar.volume
                _arr_symbol[_widx] = bar.symbol
                _arr_timestamp[_widx] = bar.timestamp
                if _filled < window_size:
                    _filled += 1
                _head = (_head + 1) % window_size
            else:
                _window_data.append(bar.to_dict())

            session.bar_count += 1

            # Warmup phase
            if not warmup_done:
                if config.warmup_bars > 0 and session.bar_count < config.warmup_bars:
                    continue
                warmup_done = True

            # Build window DataFrame from circular buffer.
            # When buffer is full, reorder from _head to get chronological order.
            # pd.DataFrame(dict_of_arrays) is ~10-20x faster than pd.DataFrame(list_of_dicts).
            #
            # P2-6 NOTE: A new DataFrame is constructed every bar iteration.
            # This is intentional — the FeaturePipeline expects a fresh DataFrame
            # and may mutate it. Profiling shows the numpy array slicing is O(1)
            # and DataFrame construction is O(window_size), which is acceptable
            # for typical window sizes (20-200). For very large windows (500+),
            # consider incremental DataFrame updates or a view-based approach.
            if window_size > 0:
                if _filled < window_size:
                    # Still growing — data is already in chronological order
                    window_df = pd.DataFrame({
                        "open": _arr_open[:_filled],
                        "high": _arr_high[:_filled],
                        "low": _arr_low[:_filled],
                        "close": _arr_close[:_filled],
                        "volume": _arr_volume[:_filled],
                        "symbol": _arr_symbol[:_filled],
                        "timestamp": _arr_timestamp[:_filled],
                    })
                else:
                    # Circular buffer full — reorder from oldest to newest
                    _idx = np.arange(_head - window_size, _head) % window_size
                    window_df = pd.DataFrame({
                        "open": _arr_open[_idx],
                        "high": _arr_high[_idx],
                        "low": _arr_low[_idx],
                        "close": _arr_close[_idx],
                        "volume": _arr_volume[_idx],
                        "symbol": _arr_symbol[_idx],
                        "timestamp": _arr_timestamp[_idx],
                    })
            else:
                window_df = pd.DataFrame(_window_data)

            features = self._run_features(window_df, session, config)
            if features is None:
                equity = session.current_equity
                session.equity_curve.append((bar_ts, equity))
                if equity > session.peak_equity:
                    session.peak_equity = equity
                continue

            candidate = Candidate(symbol=symbol, score=50.0, reasons=["replay"])

            if session.has_position(bar.symbol):
                meta = session.position_meta.get(bar.symbol)
                hit_stop = meta is not None and meta.stop_loss is not None and bar.low <= meta.stop_loss
                hit_target = meta is not None and meta.target is not None and bar.high >= meta.target

                if hit_stop or hit_target:
                    reason = "Stop-loss hit" if hit_stop else "Target hit"
                    exit_price = meta.stop_loss if hit_stop else meta.target
                    self._close_position_at_price(session, bar, exit_price, reason)
                    # Skip signal processing for this bar - position already closed
                    # Update equity and continue to next bar
                    equity = session.current_equity
                    session.equity_curve.append((bar_ts, equity))
                    if equity > session.peak_equity:
                        session.peak_equity = equity
                    continue

            # Run StrategyPipeline
            signals = self._strategy.evaluate_single(candidate, features)

            # Process signals (P0-2: routes through OMS if available)
            for signal in signals:
                session.signals.append(signal)
                if config.fill_model == FillModel.NEXT_OPEN:
                    pending_signals.append((signal, bar))
                else:
                    self._process_signal(signal, bar, session, config)
                    if config.publish_events and self._event_bus is not None:
                        self._publish_signal(signal)

            if session.has_position(bar.symbol):
                session.mark_symbol(bar.symbol, float(bar.close))

            # Update equity
            equity = session.current_equity
            session.equity_curve.append((bar_ts, equity))
            if equity > session.peak_equity:
                session.peak_equity = equity

        if session.has_position(bar.symbol):
            self._close_position(session, bar, "End of replay")

        # Process any remaining pending signals (next-bar-open with no next bar)
        if pending_signals:
            for sig, _sig_bar in pending_signals:
                self._process_signal(sig, bar, session, config, fill_price=bar.open)
                if config.publish_events and self._event_bus is not None:
                    self._publish_signal(sig)

        return ReplayResult(
            session=session,
            config=config,
            bars_processed=session.bar_count,
            signals_generated=len(session.signals),
        )

    # ------------------------------------------------------------------
    # Multi-symbol replay
    # ------------------------------------------------------------------

    def _run_multi_symbol(self, df: pd.DataFrame, ts_col: str) -> ReplayResult:
        """Process multiple symbols chronologically with shared capital."""
        config = self._config
        session = ReplaySession(capital=config.initial_capital)
        session.peak_equity = config.initial_capital
        session.equity_curve.append((df[ts_col].iloc[0], config.initial_capital))

        window_size = config.window_size if config.window_size > 0 else 0
        window_states: dict[str, dict] = {}
        symbol_bar_counts: dict[str, int] = {}
        warmup_done: dict[str, bool] = {}
        pending_signals: dict[str, list[tuple[Signal, HistoricalBar]]] = {}
        last_bars: dict[str, HistoricalBar] = {}

        for idx in range(len(df)):
            row = df.iloc[idx]
            bar_ts = row[ts_col]
            symbol = str(row["symbol"])

            bar = HistoricalBar.from_replay(
                symbol=symbol,
                timestamp=bar_ts,
                open=float(row.get("open", 0)),
                high=float(row.get("high", 0)),
                low=float(row.get("low", 0)),
                close=float(row.get("close", 0)),
                volume=float(row.get("volume", 0)),
            )
            last_bars[symbol] = bar

            if self._event_schedule and self._event_bus is not None:
                self._publish_scheduled_events(bar_ts)

            sym_pending = pending_signals.setdefault(symbol, [])
            if sym_pending:
                for sig, _sig_bar in sym_pending:
                    self._process_signal(sig, bar, session, config, fill_price=bar.open)
                    if config.publish_events and self._event_bus is not None:
                        self._publish_signal(sig)
                sym_pending.clear()

            if symbol not in window_states:
                window_states[symbol] = self._new_window_state(window_size)
            self._append_bar_window(window_states[symbol], bar)

            session.bar_count += 1
            symbol_bar_counts[symbol] = symbol_bar_counts.get(symbol, 0) + 1

            if not warmup_done.get(symbol, False):
                if config.warmup_bars > 0 and symbol_bar_counts[symbol] < config.warmup_bars:
                    continue
                warmup_done[symbol] = True

            window_df = self._window_dataframe(window_states[symbol])
            features = self._run_features(window_df, session, config)
            if features is None:
                equity = session.current_equity
                session.equity_curve.append((bar_ts, equity))
                if equity > session.peak_equity:
                    session.peak_equity = equity
                continue

            candidate = Candidate(symbol=symbol, score=50.0, reasons=["replay"])

            if session.has_position(bar.symbol):
                meta = session.position_meta.get(bar.symbol)
                hit_stop = meta is not None and meta.stop_loss is not None and bar.low <= meta.stop_loss
                hit_target = meta is not None and meta.target is not None and bar.high >= meta.target

                if hit_stop or hit_target:
                    reason = "Stop-loss hit" if hit_stop else "Target hit"
                    exit_price = meta.stop_loss if hit_stop else meta.target
                    self._close_position_at_price(session, bar, exit_price, reason)
                    equity = session.current_equity
                    session.equity_curve.append((bar_ts, equity))
                    if equity > session.peak_equity:
                        session.peak_equity = equity
                    continue

            signals = self._strategy.evaluate_single(candidate, features)
            for signal in signals:
                session.signals.append(signal)
                if config.fill_model == FillModel.NEXT_OPEN:
                    sym_pending.append((signal, bar))
                else:
                    self._process_signal(signal, bar, session, config)
                    if config.publish_events and self._event_bus is not None:
                        self._publish_signal(signal)

            if session.has_position(bar.symbol):
                session.mark_symbol(bar.symbol, float(bar.close))

            equity = session.current_equity
            session.equity_curve.append((bar_ts, equity))
            if equity > session.peak_equity:
                session.peak_equity = equity

        for symbol, bar in last_bars.items():
            if session.has_position(symbol):
                self._close_position(session, bar, "End of replay")

        for symbol, sym_pending in pending_signals.items():
            if not sym_pending:
                continue
            bar = last_bars.get(symbol)
            if bar is None:
                continue
            for sig, _sig_bar in sym_pending:
                self._process_signal(sig, bar, session, config, fill_price=bar.open)
                if config.publish_events and self._event_bus is not None:
                    self._publish_signal(sig)

        return ReplayResult(
            session=session,
            config=config,
            bars_processed=session.bar_count,
            signals_generated=len(session.signals),
        )

    # ------------------------------------------------------------------
    # Window management (circular buffer helpers)
    # ------------------------------------------------------------------

    def _new_window_state(self, window_size: int) -> dict:
        """Create per-symbol sliding window state."""
        if window_size > 0:
            return {
                "size": window_size,
                "open": np.empty(window_size, dtype=np.float64),
                "high": np.empty(window_size, dtype=np.float64),
                "low": np.empty(window_size, dtype=np.float64),
                "close": np.empty(window_size, dtype=np.float64),
                "volume": np.empty(window_size, dtype=np.float64),
                "symbol": np.empty(window_size, dtype=object),
                "timestamp": np.empty(window_size, dtype="datetime64[ns]"),
                "filled": 0,
                "head": 0,
            }
        return {"size": 0, "data": deque()}

    def _append_bar_window(self, state: dict, bar: HistoricalBar) -> None:
        """Append a bar to per-symbol window state (O(1) ring buffer)."""
        window_size = state["size"]
        if window_size > 0:
            widx = state["head"]
            state["open"][widx] = bar.open
            state["high"][widx] = bar.high
            state["low"][widx] = bar.low
            state["close"][widx] = bar.close
            state["volume"][widx] = bar.volume
            state["symbol"][widx] = bar.symbol
            state["timestamp"][widx] = bar.timestamp
            if state["filled"] < window_size:
                state["filled"] += 1
            state["head"] = (state["head"] + 1) % window_size
        else:
            state["data"].append(bar.to_dict())

    def _window_dataframe(self, state: dict) -> pd.DataFrame:
        """Build a feature-pipeline window DataFrame from per-symbol state."""
        window_size = state["size"]
        if window_size > 0:
            filled = state["filled"]
            if filled < window_size:
                return pd.DataFrame({
                    "open": state["open"][:filled],
                    "high": state["high"][:filled],
                    "low": state["low"][:filled],
                    "close": state["close"][:filled],
                    "volume": state["volume"][:filled],
                    "symbol": state["symbol"][:filled],
                    "timestamp": state["timestamp"][:filled],
                })
            head = state["head"]
            idx = np.arange(head - window_size, head) % window_size
            return pd.DataFrame({
                "open": state["open"][idx],
                "high": state["high"][idx],
                "low": state["low"][idx],
                "close": state["close"][idx],
                "volume": state["volume"][idx],
                "symbol": state["symbol"][idx],
                "timestamp": state["timestamp"][idx],
            })
        return pd.DataFrame(state["data"])

    def _build_window(self, window_data, window_size: int) -> pd.DataFrame:
        """Build a DataFrame from the window data (deprecated by REF-022 ring buffer).

        Retained for backward compatibility with external callers.
        """
        # If it's a deque with maxlen, it's already bounded
        # If it's a list and window_size > 0, slice it
        if isinstance(window_data, list) and window_size > 0:
            window_data = window_data[-window_size:]
        return pd.DataFrame(window_data)

    # ------------------------------------------------------------------
    # Event publishing
    # ------------------------------------------------------------------

    def _publish_scheduled_events(self, bar_ts: pd.Timestamp) -> None:
        """Publish any scheduled events with timestamp <= current bar timestamp.

        P0-1 fix: Events from the event log are published in time order relative
        to bar processing, ensuring deterministic replay that matches the original
        event/bar interleaving. Events scheduled at or before the current bar's
        timestamp are published before the bar is processed.

        Parameters
        ----------
        bar_ts:
            Timestamp of the current bar being processed.
        """
        # Iterate without mutating the schedule (non-destructive .get())
        # so the engine can be reused for multiple replays.
        scheduled_ts = sorted(self._event_schedule.keys())
        for evt_ts in scheduled_ts:
            if evt_ts > bar_ts:
                break
            events = self._event_schedule.get(evt_ts)
            if events is None:
                continue
            for event in events:
                try:
                    self._event_bus.publish(event)
                except Exception as exc:
                    logger.debug("Failed to publish scheduled event at %s: %s", evt_ts, exc)

    def _publish_signal(self, signal: Signal) -> None:
        """Publish a signal to the EventBus.

        Builds a canonical DomainEvent with the ``SIGNAL_GENERATED`` event type
        so consumers on the bus (metrics, audit, strategies) can react.  Errors
        are swallowed because signal publishing is best-effort; a failed publish
        must never abort the replay bar loop.
        """
        try:
            from domain.events import EventType
            from domain.runtime_hooks import create_domain_event

            event = create_domain_event(
                event_type=EventType.SIGNAL_GENERATED.value,
                payload={
                    "symbol": signal.symbol,
                    "strategy": signal.strategy,
                    "signal_type": signal.signal_type.value
                    if hasattr(signal.signal_type, "value")
                    else str(signal.signal_type),
                    "score": getattr(signal, "score", None),
                    "confidence": getattr(signal, "confidence", None),
                },
                symbol=signal.symbol,
                source=f"replay:{signal.strategy}",
            )
            self._event_bus.publish(event)
        except Exception as exc:
            logger.debug("Failed to publish signal event: %s", exc)
