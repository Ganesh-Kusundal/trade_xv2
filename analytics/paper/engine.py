"""PaperTradingEngine — same pipeline as live, simulated fills.

Processes OHLCV data (historical or live bars) through the same
FeaturePipeline + StrategyPipeline as live trading. Simulates order
execution with slippage and commission. Supports single and multi-symbol.

This ensures parity: if a strategy works in paper, it works in live.

Flow per bar:
    1. Receive Bar (OHLCV)
    2. Append to growing window (sliding window)
    3. Run FeaturePipeline on the window
    4. Construct Candidate from latest bar
    5. Run StrategyPipeline.evaluate_single(candidate, features)
    6. Process Signals → place orders → fill at bar close ± slippage
    7. Update positions, equity curve

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
import uuid
from datetime import datetime

import pandas as pd

from analytics.paper.models import (
    OrderSide,
    OrderStatus,
    PaperConfig,
    PaperOrder,
    PaperPosition,
    PaperResult,
    PaperSession,
    PaperTrade,
    PositionSide,
)
from analytics.pipeline.pipeline import FeaturePipeline
from analytics.replay.models import Bar
from analytics.scanner.models import Candidate
from analytics.strategy.models import Signal
from analytics.strategy.pipeline import StrategyPipeline

logger = logging.getLogger(__name__)


def _gen_id() -> str:
    return uuid.uuid4().hex[:8]


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
        pipeline: FeaturePipeline,
        strategy_pipeline: StrategyPipeline | None = None,
        config: PaperConfig | None = None,
    ) -> None:
        self._pipeline = pipeline
        self._strategy = strategy_pipeline or StrategyPipeline()
        self._config = config or PaperConfig()

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
            "timestamp"
            if "timestamp" in df.columns
            else "date" if "date" in df.columns else None
        )
        if ts_col is None:
            raise ValueError("Data must have a 'timestamp' or 'date' column")

        df[ts_col] = pd.to_datetime(df[ts_col])
        df = df.sort_values(ts_col).reset_index(drop=True)

        if "symbol" in df.columns:
            return self._run_multi_symbol(df, ts_col)

        return self._run_single(df, symbol, ts_col)

    def on_bar(self, bar: Bar, session: PaperSession) -> list[Signal]:
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

        # Check stop-loss / take-profit on existing positions
        self._check_exits(bar, session)

        # Update position prices
        for pos in session.positions.values():
            if pos.symbol == bar.symbol:
                pos.update_price(bar.close)

        # Skip warmup
        if session.bar_count < self._config.warmup_bars:
            return []

        # Build window
        if not hasattr(session, "_window"):
            session._window = []  # type: ignore[attr-defined]
        session._window.append(bar.to_dict())  # type: ignore[attr-defined]

        window_df = self._build_window(
            session._window, self._config.window_size  # type: ignore[attr-defined]
        )

        # Run FeaturePipeline
        try:
            features = self._pipeline.run(window_df) if self._pipeline is not None else window_df
        except Exception as exc:
            logger.warning("FeaturePipeline failed at bar %d: %s", session.bar_count, exc)
            features = window_df

        # Construct Candidate
        candidate = Candidate(symbol=bar.symbol, score=50.0, reasons=["live"])

        # Run StrategyPipeline
        signals = self._strategy.evaluate_single(candidate, features) if self._strategy is not None else []

        # Process signals
        for signal in signals:
            self._process_signal(signal, bar, session)

        # Update equity
        equity = session.total_equity
        session.equity_curve.append((bar.timestamp, equity))
        if equity > session.peak_equity:
            session.peak_equity = equity

        return signals

    # -----------------------------------------------------------------------
    # Batch run (historical or replayed bars)
    # -----------------------------------------------------------------------

    def _run_single(self, df: pd.DataFrame, symbol: str, ts_col: str) -> PaperResult:
        """Process a single symbol's data bar-by-bar."""
        config = self._config
        session = PaperSession(capital=config.initial_capital)
        session.peak_equity = config.initial_capital
        session.equity_curve.append((df[ts_col].iloc[0], config.initial_capital))
        session._window = []  # type: ignore[attr-defined]

        window: list[dict] = []
        warmup_done = False
        signals_all: list[Signal] = []

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

            # Check stop-loss / take-profit
            self._check_exits(bar, session)

            # Update position prices
            for pos in session.positions.values():
                if pos.symbol == bar.symbol:
                    pos.update_price(bar.close)

            # Build window DataFrame
            window_df = self._build_window(window, config.window_size)

            # Run FeaturePipeline
            try:
                features = self._pipeline.run(window_df) if self._pipeline is not None else window_df
            except Exception as exc:
                logger.warning(
                    "FeaturePipeline failed at bar %d: %s", session.bar_count, exc
                )
                features = window_df

            # Construct Candidate
            candidate = Candidate(symbol=symbol, score=50.0, reasons=["paper"])

            # Run StrategyPipeline
            signals = self._strategy.evaluate_single(candidate, features) if self._strategy is not None else []

            # Process signals
            for signal in signals:
                signals_all.append(signal)
                self._process_signal(signal, bar, session)

                # Update equity
                equity = session.total_equity
                session.equity_curve.append((bar_ts, equity))
                if equity > session.peak_equity:
                    session.peak_equity = equity

        # Close any open positions at end
        if window:
            last_bar = Bar(**window[-1])
            for sym in list(session.positions.keys()):
                self._close_position(sym, last_bar.close, last_bar.timestamp, session, "End of paper trading")

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
        session._window = {}  # type: ignore[attr-defined]

        symbols = df["symbol"].unique()
        all_signals: list[Signal] = []

        # Build per-symbol windows
        for sym in symbols:
            sym_df = df[df["symbol"] == sym].sort_values(ts_col).reset_index(drop=True)

            window: list[dict] = []
            warmup_done = False

            for idx in range(len(sym_df)):
                row = sym_df.iloc[idx]
                bar_ts = row[ts_col]

                bar = Bar(
                    symbol=sym,
                    timestamp=bar_ts,
                    open=float(row.get("open", 0)),
                    high=float(row.get("high", 0)),
                    low=float(row.get("low", 0)),
                    close=float(row.get("close", 0)),
                    volume=float(row.get("volume", 0)),
                )

                window.append(bar.to_dict())
                session.bar_count += 1

                # Warmup
                if not warmup_done:
                    if config.warmup_bars > 0 and session.bar_count < config.warmup_bars:
                        continue
                    warmup_done = True

                # Check exits
                self._check_exits(bar, session)

                # Update prices
                for pos in session.positions.values():
                    if pos.symbol == sym:
                        pos.update_price(bar.close)

                # Feature pipeline
                window_df = self._build_window(window, config.window_size)
                try:
                    features = self._pipeline.run(window_df) if self._pipeline is not None else window_df
                except Exception as exc:
                    logger.warning("FeaturePipeline failed for %s: %s", sym, exc)
                    features = window_df

                candidate = Candidate(symbol=sym, score=50.0, reasons=["paper"])
                signals = self._strategy.evaluate_single(candidate, features) if self._strategy is not None else []

                for signal in signals:
                    all_signals.append(signal)
                    self._process_signal(signal, bar, session)

                equity = session.total_equity
                session.equity_curve.append((bar_ts, equity))
                if equity > session.peak_equity:
                    session.peak_equity = equity

        # Close remaining positions
        if window:
            last_bar = Bar(**window[-1])
            for sym in list(session.positions.keys()):
                self._close_position(sym, last_bar.close, last_bar.timestamp, session, "End")

        return PaperResult(
            session=session,
            config=config,
            bars_processed=session.bar_count,
            signals_generated=len(all_signals),
        )

    # -----------------------------------------------------------------------
    # Signal processing
    # -----------------------------------------------------------------------

    def _process_signal(self, signal: Signal, bar: Bar, session: PaperSession) -> None:
        """Process a signal: open/close positions, record orders."""
        if not signal.is_actionable:
            return

        if signal.is_buy:
            self._open_position(bar, session, signal)
        elif signal.is_sell:
            # Close matching position
            if bar.symbol in session.positions:
                pos = session.positions[bar.symbol]
                if pos.side == PositionSide.LONG:
                    self._close_position(bar.symbol, bar.close, bar.timestamp, session, "Signal sell")
                elif pos.side == PositionSide.SHORT:
                    # Short covering
                    self._close_position(bar.symbol, bar.close, bar.timestamp, session, "Signal cover")

    def _open_position(self, bar: Bar, session: PaperSession, signal: Signal) -> None:
        """Open a new position."""
        config = self._config

        # Check position limits
        if session.position_count >= config.max_positions:
            return

        # Check if already have position in this symbol
        if bar.symbol in session.positions:
            return

        # Calculate position size
        price = bar.close * (1 + config.slippage_pct / 100)
        max_notional = session.total_equity * (config.max_position_pct / 100)
        qty = int(max_notional / price) if price > 0 else 0

        if qty <= 0:
            return

        # Calculate costs
        trade_value = qty * price
        commission = max(trade_value * config.commission_pct, config.commission_flat)
        slippage_cost = qty * bar.close * (config.slippage_pct / 100)

        # Check if can afford
        total_cost = trade_value + commission
        if total_cost > session.capital:
            return

        # Deduct capital
        session.capital -= total_cost

        # Create order
        order = PaperOrder(
            order_id=f"P-{_gen_id()}",
            symbol=bar.symbol,
            side=OrderSide.BUY,
            quantity=qty,
            price=bar.close,
            order_time=bar.timestamp,
            status=OrderStatus.FILLED,
            fill_price=price,
            fill_time=bar.timestamp,
            commission=commission,
            slippage=slippage_cost,
            strategy=signal.strategy,
            reasons=[signal.signal_type.value, *signal.reasons],
        )
        session.orders.append(order)

        # Create position
        session.positions[bar.symbol] = PaperPosition(
            symbol=bar.symbol,
            side=PositionSide.LONG,
            entry_price=price,
            quantity=qty,
            entry_time=bar.timestamp,
            current_price=bar.close,
            stop_loss=signal.stop_loss,
            take_profit=signal.target,
            strategy=signal.strategy,
        )

    def _close_position(
        self,
        symbol: str,
        price: float,
        timestamp: datetime,
        session: PaperSession,
        reason: str,
    ) -> None:
        """Close a position and record the trade."""
        config = self._config
        if symbol not in session.positions:
            return

        pos = session.positions[symbol]

        # Calculate exit price with slippage
        if pos.side == PositionSide.LONG:
            exit_price = price * (1 - config.slippage_pct / 100)
        else:
            exit_price = price * (1 + config.slippage_pct / 100)

        # Calculate P&L
        if pos.side == PositionSide.LONG:
            pnl = (exit_price - pos.entry_price) * pos.quantity
        else:
            pnl = (pos.entry_price - exit_price) * pos.quantity

        pnl_pct = (
            ((exit_price / pos.entry_price) - 1) * 100
            if pos.entry_price > 0
            else 0.0
        )
        if pos.side == PositionSide.SHORT:
            pnl_pct = -pnl_pct

        # Calculate commission
        exit_value = exit_price * pos.quantity
        commission = max(exit_value * config.commission_pct, config.commission_flat)
        slippage_cost = pos.quantity * price * (config.slippage_pct / 100)

        # Net P&L
        net_pnl = pnl - commission

        # Return capital
        session.capital += pos.quantity * pos.entry_price + net_pnl

        # Record trade
        session.trades.append(
            PaperTrade(
                symbol=symbol,
                side=OrderSide.BUY if pos.side == PositionSide.LONG else OrderSide.SELL,
                entry_price=pos.entry_price,
                exit_price=exit_price,
                quantity=pos.quantity,
                entry_time=pos.entry_time,
                exit_time=timestamp,
                pnl=net_pnl,
                pnl_pct=pnl_pct,
                commission=commission,
                slippage_cost=slippage_cost,
                strategy=pos.strategy,
                reasons=[reason],
            )
        )

        # Record exit order
        session.orders.append(
            PaperOrder(
                order_id=f"P-{_gen_id()}",
                symbol=symbol,
                side=OrderSide.SELL if pos.side == PositionSide.LONG else OrderSide.BUY,
                quantity=pos.quantity,
                price=price,
                order_time=timestamp,
                status=OrderStatus.FILLED,
                fill_price=exit_price,
                fill_time=timestamp,
                commission=commission,
                slippage=slippage_cost,
                strategy=pos.strategy,
                reasons=[reason],
            )
        )

        # Remove position
        del session.positions[symbol]

    def _check_exits(self, bar: Bar, session: PaperSession) -> None:
        """Check stop-loss and take-profit exits for all positions."""
        if bar.symbol not in session.positions:
            return

        pos = session.positions[bar.symbol]

        # Stop-loss check
        if pos.stop_loss is not None:
            if pos.side == PositionSide.LONG and bar.low <= pos.stop_loss or pos.side == PositionSide.SHORT and bar.high >= pos.stop_loss:
                self._close_position(bar.symbol, pos.stop_loss, bar.timestamp, session, "Stop-loss hit")
                return

        # Take-profit check
        if pos.take_profit is not None:
            if pos.side == PositionSide.LONG and bar.high >= pos.take_profit or pos.side == PositionSide.SHORT and bar.low <= pos.take_profit:
                self._close_position(bar.symbol, pos.take_profit, bar.timestamp, session, "Take-profit hit")
                return

    # -----------------------------------------------------------------------
    # Helpers
    # -----------------------------------------------------------------------

    def _build_window(self, window: list[dict], window_size: int) -> pd.DataFrame:
        """Build a DataFrame from the window, optionally limiting size."""
        if window_size > 0:
            window = window[-window_size:]
        return pd.DataFrame(window)
