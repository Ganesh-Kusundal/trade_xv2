"""PaperTradingEngine — same pipeline as live, simulated fills.

Processes OHLCV data (historical or live bars) through the same
FeaturePipeline + StrategyPipeline as live trading. Simulates order
execution with slippage and commission. Supports single and multi-symbol.

This ensures parity: if a strategy works in paper, it works in live.

Flow per bar:
    1. Receive bar (OHLCV)
    2. Append to growing window (sliding window)
    3. Run FeaturePipeline on the window
    4. Construct Candidate from latest bar
    5. Run StrategyPipeline.evaluate_single(candidate, features)
    6. Process Signals → place orders → fill at bar close ± slippage
    7. Update positions, equity curve

Responsibility split (this file is the facade):
    * Bar iteration / window building  -> ``BarWindowManager``
    * Signal processing (OMS routing)  -> ``PaperSignalProcessor``
    * Position closing / exit checks   -> ``PaperPositionCloser``

Usage:
    from analytics.paper import PaperTradingEngine, PaperConfig
    from analytics.pipeline import FeaturePipeline, RSI, ATR, SMA
    from analytics.strategy import StrategyPipeline, MomentumStrategy

    pipeline = FeaturePipeline().add(RSI(14)).add(ATR(14)).add(SMA(20))
    strategy = StrategyPipeline(strategies=[MomentumStrategy()])
    config = PaperConfig(initial_capital=100_000, max_positions=3)

    engine = PaperTradingEngine(pipeline, strategy, config)
    result = engine.run(dataframe, symbol="RELIANCE")
    print(result.summary)
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from datetime import datetime
from decimal import Decimal

import pandas as pd

from analytics.paper.bar_window import BarWindowManager
from analytics.paper.models import PaperConfig, PaperResult, PaperSession
from analytics.paper.position_closer import PaperPositionCloser
from analytics.paper.signal_processor import PaperSignalProcessor
from analytics.pipeline.pipeline import FeaturePipeline
from analytics.replay.models import FillModel
from analytics.scanner.models import Candidate
from analytics.strategy.models import Signal
from analytics.strategy.pipeline import StrategyPipeline
from analytics.strategy.registry import StrategyRegistry
from domain import Side
from domain.candles.historical import HistoricalBar
from domain.entities import Trade
from domain.ports.oms_backtest_adapter import OmsBacktestAdapterPort
from runtime.replay_factory import get_oms_backtest_factory

logger = logging.getLogger(__name__)


class PaperTradingEngine:
    """Paper trading engine — same pipeline as live, simulated fills.

    Processes OHLCV data bar-by-bar through FeaturePipeline + StrategyPipeline.
    Simulates order execution at bar close with configurable slippage and commission.
    Supports single and multi-symbol trading.

    Parameters
    ----------
    pipeline:
        FeaturePipeline for computing indicators on each window.
    strategy_pipeline:
        StrategyPipeline for evaluating candidates on each bar.
    config:
        Paper trading configuration (capital, slippage, position limits, etc.).
    """

    def __init__(
        self,
        pipeline: FeaturePipeline | None = None,
        strategy_pipeline: StrategyPipeline | None = None,
        config: PaperConfig | None = None,
        trading_context=None,
        execution_adapter=None,
        oms_adapter: OmsBacktestAdapterPort | None = None,
    ) -> None:
        self._pipeline = pipeline or FeaturePipeline()
        self._strategy = strategy_pipeline or StrategyPipeline()
        StrategyRegistry.self_check(self._strategy.strategies)
        self._config = config or PaperConfig()
        self._trading_context = trading_context
        self._oms_adapter: OmsBacktestAdapterPort | None = None
        if oms_adapter is not None:
            self._oms_adapter = oms_adapter
        elif trading_context is not None:
            self._oms_adapter = get_oms_backtest_factory()(
                trading_context,
                mode="paper",
                slippage_pct=self._config.slippage_pct,
                commission_flat=self._config.commission_flat,
                execution_adapter=execution_adapter,
            )
        else:
            raise TypeError(
                "PaperTradingEngine requires trading_context (or oms_adapter) for order execution. "
                "Pass a TradingContext instance from your composition root."
            )

        # Decompose responsibilities into focused collaborators. The fill-recording
        # callback is shared so every collaborator applies fills through the same
        # FillReducer / PortfolioProjector path.
        self._window_mgr = BarWindowManager(self._pipeline)
        self._signal_processor = PaperSignalProcessor(
            self._config, self._oms_adapter, self._record_session_fill
        )
        self._closer = PaperPositionCloser(
            self._config, self._oms_adapter, self._record_session_fill
        )

    # -----------------------------------------------------------------------
    # Public API
    # -----------------------------------------------------------------------

    def run(self, data: pd.DataFrame, *, symbol: str = "SYMBOL") -> PaperResult:
        """Run paper trading on OHLCV DataFrame.

        Parameters
        ----------
        data:
            DataFrame with columns: timestamp/date, open, high, low, close, volume.
            If multiple symbols, must have a 'symbol' column.
        symbol:
            Symbol name if data doesn't have a 'symbol' column.

        Returns
        -------
        PaperResult with all orders, trades, positions, equity curve, and metrics.
        """
        if data.empty:
            return PaperResult(config=self._config)

        df = data.copy()
        ts_col = (
            "timestamp" if "timestamp" in df.columns else "date" if "date" in df.columns else None
        )
        if ts_col is None:
            raise ValueError("Data must have a 'timestamp' or 'date' column")

        df[ts_col] = pd.to_datetime(df[ts_col])
        df = df.sort_values(ts_col).reset_index(drop=True)

        if "symbol" in df.columns:
            return self._run_multi_symbol(df, ts_col)

        return self._run_single(df, symbol, ts_col)

    def on_bar(self, bar: HistoricalBar, session: PaperSession) -> list[Signal]:
        """Process a single live bar. Call this for real-time streaming.

        Parameters
        ----------
        bar:
            New OHLCV bar from live feed.
        session:
            Active PaperSession to update.

        Returns
        -------
        List of signals generated from this bar.
        """
        session.bar_count += 1

        # Flush NEXT_OPEN pending from prior bar at this bar's open
        pending: list[tuple[Signal, HistoricalBar]] = getattr(session, "_pending_signals", [])
        if pending:
            for sig, _sig_bar in pending:
                self._signal_processor.process(sig, bar, session, fill_price=bar.open)
            pending.clear()

        # Check stop-loss / take-profit on existing positions
        self._closer.check_exits(session, bar)

        if session.has_position(bar.symbol):
            session.mark_symbol(bar.symbol, bar.close)

        # Skip warmup
        if session.bar_count < self._config.warmup_bars:
            return []

        # Build window
        if not hasattr(session, "_window"):
            session._window = []  # type: ignore[attr-defined]
        session._window.append(bar.to_dict())  # type: ignore[attr-defined]

        window_df = self._window_mgr.build_window(
            session._window,
            self._config.window_size,  # type: ignore[attr-defined]
        )

        features = self._window_mgr.run_features(window_df, session, self._config)
        if features is None:
            return []

        # Construct Candidate
        candidate = Candidate(symbol=bar.symbol, score=50.0, reasons=["live"])

        # Run StrategyPipeline
        signals = self._strategy.evaluate_single(candidate, features)

        # Process signals (NEXT_OPEN defers to next bar open — same as ReplayEngine)
        if not hasattr(session, "_pending_signals"):
            session._pending_signals = []  # type: ignore[attr-defined]
        for signal in signals:
            if self._config.fill_model == FillModel.NEXT_OPEN:
                session._pending_signals.append((signal, bar))  # type: ignore[attr-defined]
            else:
                self._signal_processor.process(signal, bar, session)

        # Update equity
        equity = session.total_equity
        session.equity_curve.append((bar.timestamp, equity))
        if equity > session.peak_equity:
            session.peak_equity = equity

        return signals

    # -----------------------------------------------------------------------
    # Batch run (historical or replayed bars)
    # -----------------------------------------------------------------------

    def _process_bar_stream(
        self,
        bars: Iterator[HistoricalBar],
        session: PaperSession,
    ) -> list[Signal]:
        """Shared bar-processing loop — extracted from ``_run_single`` and
        ``_run_multi_symbol`` (REF-002 DRY remediation).

        For each ``HistoricalBar`` yielded by *bars*:
        1. Flush pending NEXT_OPEN signals at this bar's open.
        2. Append to a growing sliding window.
        3. Skip warmup bars.
        4. Check stop-loss / take-profit exits.
        5. Update position mark-to-market prices.
        6. Run the feature pipeline to compute indicators.
        7. Construct a ``Candidate`` and evaluate it through the strategy pipeline.
        8. Process every actionable signal (or defer for NEXT_OPEN).
        9. Record the resulting equity in the session's equity curve.

        Parameters
        ----------
        bars:
            Iterator that yields :class:`HistoricalBar` instances in chronological order.
        session:
            Mutable :class:`PaperSession` updated in-place.

        Returns
        -------
        list[Signal]:
            Every signal generated during the run (for audit / metrics).
        """
        config = self._config
        window: list[dict] = []
        warmup_done = False
        signals_all: list[Signal] = []
        # symbol -> pending (signal, bar) for FillModel.NEXT_OPEN
        pending_by_symbol: dict[str, list[tuple[Signal, HistoricalBar]]] = {}
        last_bars: dict[str, HistoricalBar] = {}

        for bar in bars:
            last_bars[bar.symbol] = bar
            window.append(bar.to_dict())
            session.bar_count += 1

            # Flush prior-bar NEXT_OPEN signals at this bar's open
            sym_pending = pending_by_symbol.setdefault(bar.symbol, [])
            if sym_pending:
                for sig, _sig_bar in sym_pending:
                    self._signal_processor.process(sig, bar, session, fill_price=bar.open)
                sym_pending.clear()

            # Warmup phase — skip bars until the warmup window is full
            if not warmup_done:
                if config.warmup_bars > 0 and session.bar_count < config.warmup_bars:
                    continue
                warmup_done = True

            # Check stop-loss / take-profit exits and update mark-to-market
            self._closer.check_exits(session, bar)
            if session.has_position(bar.symbol):
                session.mark_symbol(bar.symbol, bar.close)

            # Build window DataFrame and run feature pipeline
            window_df = self._window_mgr.build_window(window, config.window_size)
            features = self._window_mgr.run_features(window_df, session, config)
            if features is None:
                equity = session.total_equity
                session.equity_curve.append((bar.timestamp, equity))
                if equity > session.peak_equity:
                    session.peak_equity = equity
                continue

            # Construct candidate and evaluate through strategy pipeline
            candidate = Candidate(symbol=bar.symbol, score=50.0, reasons=["paper"])
            signals = self._strategy.evaluate_single(candidate, features)

            for signal in signals:
                signals_all.append(signal)
                if config.fill_model == FillModel.NEXT_OPEN:
                    sym_pending.append((signal, bar))
                else:
                    self._signal_processor.process(signal, bar, session)

            # Record equity after all signals for this bar have been processed
            equity = session.total_equity
            session.equity_curve.append((bar.timestamp, equity))
            if equity > session.peak_equity:
                session.peak_equity = equity

        # Remaining pending: no next bar — fill at last bar open (matches ReplayEngine)
        for symbol, sym_pending in pending_by_symbol.items():
            if not sym_pending:
                continue
            fill_bar = last_bars.get(symbol)
            if fill_bar is None:
                continue
            for sig, _sig_bar in sym_pending:
                self._signal_processor.process(
                    sig, fill_bar, session, fill_price=fill_bar.open
                )
            sym_pending.clear()

        return signals_all

    def _run_single(self, df: pd.DataFrame, symbol: str, ts_col: str) -> PaperResult:
        """Process a single symbol's data bar-by-bar."""
        config = self._config
        session = PaperSession(capital=config.initial_capital)
        session.peak_equity = config.initial_capital
        session.equity_curve.append((df[ts_col].iloc[0], config.initial_capital))

        signals_all = self._process_bar_stream(
            self._window_mgr.iter_bars(df, symbol, ts_col), session
        )

        # Close any open positions at end
        if not df.empty:
            last_row = df.iloc[-1]
            last_bar = HistoricalBar.from_replay(
                symbol=symbol,
                timestamp=last_row[ts_col],
                open=float(last_row.get("open", 0)),
                high=float(last_row.get("high", 0)),
                low=float(last_row.get("low", 0)),
                close=float(last_row.get("close", 0)),
                volume=float(last_row.get("volume", 0)),
            )
            for sym in list(session.open_symbols()):
                self._closer.close(
                    session,
                    sym,
                    last_bar.close,
                    last_bar.timestamp,
                    "End of paper trading",
                )

        return PaperResult(
            session=session,
            config=config,
            bars_processed=session.bar_count,
            signals_generated=len(signals_all),
        )

    def _run_multi_symbol(self, df: pd.DataFrame, ts_col: str) -> PaperResult:
        """Process multiple symbols with shared capital."""
        config = self._config
        session = PaperSession(capital=config.initial_capital)
        session.peak_equity = config.initial_capital

        merged = df.sort_values(ts_col).reset_index(drop=True)
        if not merged.empty:
            session.equity_curve.append((merged[ts_col].iloc[0], config.initial_capital))

        all_signals = self._process_bar_stream(
            self._window_mgr.iter_bars(merged, "", ts_col), session
        )

        # Close remaining positions at each symbol's last bar price
        if not merged.empty:
            last_rows = merged.groupby("symbol", sort=False).last()
            for sym in list(session.open_symbols()):
                if sym not in last_rows.index:
                    continue
                row = last_rows.loc[sym]
                self._closer.close(
                    session,
                    sym,
                    float(row["close"]),
                    row[ts_col],
                    "End of paper trading",
                )

        return PaperResult(
            session=session,
            config=config,
            bars_processed=session.bar_count,
            signals_generated=len(all_signals),
        )

    # -----------------------------------------------------------------------
    # Session fill recording (shared with collaborators)
    # -----------------------------------------------------------------------

    def _record_session_fill(
        self,
        session: PaperSession,
        *,
        order_id: str,
        symbol: str,
        exchange: str,
        side: Side,
        quantity: int,
        price: float,
        timestamp: datetime,
        trade_tag: str,
    ) -> bool:
        """Apply paper fill through FillReducer then PortfolioProjector."""
        if not order_id or quantity <= 0:
            return False
        trade = Trade(
            trade_id=f"{order_id}:{trade_tag}",
            order_id=order_id,
            symbol=symbol,
            exchange=exchange,
            side=side,
            quantity=quantity,
            price=Decimal(str(price)),
            trade_value=Decimal(str(price)) * quantity,
            timestamp=timestamp,
        )
        return session.fill_pipeline.apply_trade(trade, order_quantity=quantity)
