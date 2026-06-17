"""ReplayEngine — bar-by-bar historical replay through FeaturePipeline + StrategyPipeline.

The engine processes OHLCV data one bar at a time, running the same
FeaturePipeline and StrategyPipeline used in live trading. This ensures
complete parity: if a strategy works in replay, it will work in live.

Flow per bar:
    1. Receive Bar (OHLCV)
    2. Append to growing DataFrame (sliding window)
    3. Run FeaturePipeline on the window
    4. Construct Candidate from latest bar
    5. Run StrategyPipeline.evaluate_single(candidate, features)
    6. Process Signals (update positions, record trades)
    7. Update equity curve

Usage:
    from analytics.pipeline import FeaturePipeline, RSI, ATR, SMA
    from analytics.strategy import StrategyPipeline, MomentumStrategy

    pipeline = FeaturePipeline().add(RSI(14)).add(ATR(14)).add(SMA(20))
    strategy = StrategyPipeline(strategies=[MomentumStrategy()])

    engine = ReplayEngine(pipeline, strategy)
    result = engine.run(dataframe)
    print(result.summary)
"""

from __future__ import annotations

import logging

import pandas as pd

from analytics.pipeline.pipeline import FeaturePipeline
from analytics.replay.models import (
    Bar,
    ReplayConfig,
    ReplayResult,
    ReplaySession,
    SimulatedPosition,
    SimulatedTrade,
)
from analytics.scanner.models import Candidate
from analytics.strategy.models import Signal
from analytics.strategy.pipeline import StrategyPipeline

logger = logging.getLogger(__name__)


class ReplayEngine:
    """Bar-by-bar historical replay engine.

    Processes OHLCV data through the same FeaturePipeline + StrategyPipeline
    used in live trading, ensuring complete parity.

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
    """

    def __init__(
        self,
        pipeline: FeaturePipeline,
        strategy_pipeline: StrategyPipeline | None = None,
        config: ReplayConfig | None = None,
        event_bus=None,
    ) -> None:
        self._pipeline = pipeline
        self._strategy = strategy_pipeline or StrategyPipeline()
        self._config = config or ReplayConfig()
        self._event_bus = event_bus

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

        df = data.copy()
        ts_col = "timestamp" if "timestamp" in df.columns else "date" if "date" in df.columns else None
        if ts_col is None:
            raise ValueError("Data must have a 'timestamp' or 'date' column")

        df[ts_col] = pd.to_datetime(df[ts_col])
        df = df.sort_values(ts_col).reset_index(drop=True)

        # If multi-symbol, group and process each
        if "symbol" in df.columns:
            return self._run_multi_symbol(df, ts_col)

        return self._run_single(df, symbol, ts_col)

    def _run_single(self, df: pd.DataFrame, symbol: str, ts_col: str) -> ReplayResult:
        """Process a single symbol's data bar-by-bar."""
        config = self._config
        session = ReplaySession(capital=config.initial_capital)
        session.peak_equity = config.initial_capital
        session.equity_curve.append((df[ts_col].iloc[0], config.initial_capital))

        window: list[dict] = []
        warmup_done = False

        for idx in range(len(df)):
            row = df.iloc[idx]
            bar_ts = row[ts_col]

            bar = Bar(
                symbol=symbol,
                timestamp=bar_ts,
                open=float(row.get("open", 0)),
                high=float(row.get("high", 0)),
                low=float(row.get("low", 0)),
                close=float(row.get("close", 0)),
                volume=float(row.get("volume", 0)),
            )

            window.append(bar.to_dict())
            session.bar_count += 1

            # Warmup phase
            if not warmup_done:
                if config.warmup_bars > 0 and session.bar_count < config.warmup_bars:
                    continue
                warmup_done = True

            # Build window DataFrame
            window_df = self._build_window(window, config.window_size)

            # Run FeaturePipeline
            try:
                features = self._pipeline.run(window_df)
            except Exception as exc:
                logger.warning("FeaturePipeline failed at bar %d: %s", session.bar_count, exc)
                features = window_df

            # Construct Candidate
            candidate = Candidate(symbol=symbol, score=50.0, reasons=["replay"])

            # Run StrategyPipeline
            signals = self._strategy.evaluate_single(candidate, features)

            # Process signals
            for signal in signals:
                session.signals.append(signal)
                self._process_signal(signal, bar, session, config)

                if config.publish_events and self._event_bus is not None:
                    self._publish_signal(signal)

            # Update equity
            equity = session.current_equity
            session.equity_curve.append((bar_ts, equity))
            if equity > session.peak_equity:
                session.peak_equity = equity

        # Close any open position at end
        if session.position is not None and window:
            last_bar = Bar(**window[-1])
            self._close_position(session, last_bar, "End of replay")

        return ReplayResult(
            session=session,
            config=config,
            bars_processed=session.bar_count,
            signals_generated=len(session.signals),
        )

    def _run_multi_symbol(self, df: pd.DataFrame, ts_col: str) -> ReplayResult:
        """Process multiple symbols, merging signals."""
        config = self._config
        session = ReplaySession(capital=config.initial_capital)
        session.peak_equity = config.initial_capital

        symbols = df["symbol"].unique()
        sessions_per_symbol: dict[str, ReplaySession] = {}

        for sym in symbols:
            sym_df = df[df["symbol"] == sym].sort_values(ts_col).reset_index(drop=True)
            result = self._run_single(sym_df, sym, ts_col)
            sessions_per_symbol[sym] = result.session

        # Merge all signals
        all_signals = []
        all_trades = []
        all_equity = []
        for sym, s in sessions_per_symbol.items():
            all_signals.extend(s.signals)
            all_trades.extend(s.trades)
            all_equity.extend(s.equity_curve)

        session.signals = all_signals
        session.trades = all_trades
        session.equity_curve = sorted(all_equity, key=lambda x: x[0])

        return ReplayResult(
            session=session,
            config=config,
            bars_processed=sum(s.bar_count for s in sessions_per_symbol.values()),
            signals_generated=len(all_signals),
        )

    def _build_window(self, window: list[dict], window_size: int) -> pd.DataFrame:
        """Build a DataFrame from the window, optionally limiting size."""
        if window_size > 0:
            window = window[-window_size:]
        return pd.DataFrame(window)

    def _process_signal(
        self,
        signal: Signal,
        bar: Bar,
        session: ReplaySession,
        config: ReplayConfig,
    ) -> None:
        """Process a signal: open/close positions, record trades."""
        if not signal.is_actionable:
            return

        if signal.is_buy and session.position is None:
            # Open long position
            price = bar.close * (1 + config.slippage_pct / 100)
            max_notional = session.capital * (config.max_position_pct / 100)
            qty = int(max_notional / price) if price > 0 else 0
            if qty > 0:
                cost = qty * price + config.commission_flat
                if cost <= session.capital:
                    session.capital -= cost
                    session.position = SimulatedPosition(
                        symbol=bar.symbol,
                        side="BUY",
                        entry_price=price,
                        quantity=qty,
                        entry_time=bar.timestamp,
                        stop_loss=signal.stop_loss,
                        target=signal.target,
                        strategy=signal.strategy,
                    )

        elif signal.is_sell and session.position is not None and session.position.side == "BUY":
            # Close long position
            self._close_position(session, bar, "Signal sell")

    def _close_position(self, session: ReplaySession, bar: Bar, reason: str) -> None:
        """Close the current position and record the trade."""
        pos = session.position
        if pos is None:
            return

        exit_price = bar.close * (1 - self._config.slippage_pct / 100)
        pnl = (exit_price - pos.entry_price) * pos.quantity - self._config.commission_flat
        pnl_pct = ((exit_price / pos.entry_price) - 1) * 100 if pos.entry_price > 0 else 0.0

        session.capital += pos.quantity * exit_price - self._config.commission_flat
        session.trades.append(SimulatedTrade(
            symbol=pos.symbol,
            side=pos.side,
            entry_price=pos.entry_price,
            exit_price=exit_price,
            quantity=pos.quantity,
            entry_time=pos.entry_time,
            exit_time=bar.timestamp,
            pnl=pnl,
            pnl_pct=pnl_pct,
            strategy=pos.strategy,
            reasons=[reason],
        ))
        session.position = None

    def _publish_signal(self, signal: Signal) -> None:
        """Publish a signal to the EventBus."""
        try:
            from dataclasses import dataclass, field
            from datetime import datetime, timezone

            @dataclass(frozen=True)
            class DomainEvent:
                timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
                source: str = ""

            event = DomainEvent(
                timestamp=signal.timestamp,
                source=f"replay:{signal.strategy}",
            )
            self._event_bus.publish(event)
        except Exception as exc:
            logger.debug("Failed to publish event: %s", exc)
