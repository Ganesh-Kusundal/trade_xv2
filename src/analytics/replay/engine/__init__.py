"""ReplayEngine — bar-by-bar historical replay through FeaturePipeline + StrategyPipeline.

The engine processes OHLCV data one bar at a time, running the same
FeaturePipeline and StrategyPipeline used in live trading. This ensures
complete parity: if a strategy works in replay, it will work in live.

Flow per bar:
    1. Receive bar (OHLCV)
    2. Append to sliding window (bounded by window_size)
    3. Run FeaturePipeline on the window
    4. Construct Candidate from latest bar
    5. Run StrategyPipeline.evaluate_single(candidate, features)
    6. P2-3: Check intra-bar stop-loss/target for open positions
    7. Process Signals via OMS adapter
    8. Update equity curve

Re-exports from sub-modules maintain backward compatibility.
"""

from __future__ import annotations

import logging
from contextlib import nullcontext

import pandas as pd

from analytics.pipeline.errors import FeaturePipelineError
from analytics.pipeline.pipeline import FeaturePipeline
from analytics.replay.engine.bar_loop import run_multi_symbol as _run_multi_symbol_fn
from analytics.replay.engine.bar_loop import run_single as _run_single_fn
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
from analytics.replay.window import (
    build_window as _build_window_fn,
)
from analytics.replay.window import (
    to_dataframe as _to_dataframe,
)
from analytics.scanner.models import Candidate
from analytics.strategy.models import Signal
from analytics.strategy.pipeline import StrategyPipeline
from analytics.strategy.registry import StrategyRegistry
from domain.analytics.statistics import StatisticsEngine
from domain.candles.historical import HistoricalBar
from domain.enums import Side
from domain.ports.oms_backtest_adapter import OmsBacktestAdapterPort
from domain.runtime_hooks import create_oms_backtest_adapter as get_oms_backtest_factory

logger = logging.getLogger(__name__)


class ReplayEngine:
    """Bar-by-bar historical replay engine.

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
        StrategyRegistry.self_check(self._strategy.strategies)
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
            self._oms_adapter = get_oms_backtest_factory(
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

        # PARITY cash ledger: single source of truth for session.capital when OMS is on.
        # Risk capital is bound to a FIXED account size (not this ledger) inside
        # run() via analytics_parity_scope so the TradingContext is never mutated
        # permanently by a replay.
        if self._oms_adapter is not None and self._portfolio_tracker is None:
            from analytics.replay.cash_ledger import SimulatedCashLedger

            self._portfolio_tracker = SimulatedCashLedger(self._config.initial_capital)

        # Sub-modules extracted for focused responsibility.
        self._fill_recorder = FillRecorder(self._config)
        self._position_closer = PositionCloser(
            self._fill_recorder,
            self._oms_adapter,
            self._portfolio_tracker,
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
        timestamp=None,
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
            signal,
            bar,
            session,
            config,
            fill_price=fill_price,
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
            signal,
            bar,
            session,
            config,
            fill_price=fill_price,
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
            signal,
            bar,
            session,
            config,
            fill_price=fill_price,
        )

    def _close_position(
        self,
        session: ReplaySession,
        bar: HistoricalBar,
        reason: str,
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

    def _feed_parity_risk_state(
        self,
        session: ReplaySession,
        bar: HistoricalBar,
    ) -> None:
        """Advance RiskManager daily_pnl from session equity (PARITY only)."""
        from analytics.replay.parity_risk import feed_parity_risk_state

        open_eq = (
            session.equity_curve[0][1] if session.equity_curve else self._config.initial_capital
        )
        feed_parity_risk_state(
            self._trading_context,
            current_equity=session.current_equity,
            open_equity=open_eq,
            bar_symbol=bar.symbol,
            bar_close=float(bar.close),
            has_position=session.has_position(bar.symbol),
        )

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
        from analytics.replay.cash_ledger import FixedAccountCapitalProvider

        if self._trading_context is not None:
            cm = self._trading_context.analytics_parity_scope(
                FixedAccountCapitalProvider(self._config.initial_capital)
            )
        else:
            cm = nullcontext()
        with cm:
            if "symbol" in df.columns:
                return _run_multi_symbol_fn(self, df, ts_col)
            return _run_single_fn(self, df, symbol, ts_col)

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


__all__ = ["ReplayEngine"]
