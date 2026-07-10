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
from collections.abc import Generator, Iterator
from datetime import datetime
from decimal import Decimal

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
from domain.orders.sizing import compute_order_quantity
from domain.ports.oms_backtest_adapter import OmsBacktestAdapterPort
from domain.runtime_hooks import create_oms_backtest_adapter
from domain.trading_costs import apply_slippage as _apply_slippage

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
        pipeline: FeaturePipeline | None = None,
        strategy_pipeline: StrategyPipeline | None = None,
        config: PaperConfig | None = None,
        trading_context=None,
        execution_adapter=None,
        oms_adapter: OmsBacktestAdapterPort | None = None,
    ) -> None:
        self._pipeline = pipeline or FeaturePipeline()
        self._strategy = strategy_pipeline or StrategyPipeline()
        self._config = config or PaperConfig()
        self._trading_context = trading_context
        self._oms_adapter: OmsBacktestAdapterPort | None = None
        if oms_adapter is not None:
            self._oms_adapter = oms_adapter
        elif trading_context is not None:
            self._oms_adapter = create_oms_backtest_adapter(
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
            session._window,
            self._config.window_size,  # type: ignore[attr-defined]
        )

        # Run FeaturePipeline
        try:
            features = self._pipeline.run(window_df)
        except Exception as exc:
            logger.warning("FeaturePipeline failed at bar %d: %s", session.bar_count, exc)
            features = window_df

        # Construct Candidate
        candidate = Candidate(symbol=bar.symbol, score=50.0, reasons=["live"])

        # Run StrategyPipeline
        signals = self._strategy.evaluate_single(candidate, features)

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

    def _process_bar_stream(
        self,
        bars: Iterator[Bar],
        session: PaperSession,
    ) -> list[Signal]:
        """Shared bar-processing loop — extracted from ``_run_single`` and
        ``_run_multi_symbol`` (REF-002 DRY remediation).

        For each ``Bar`` yielded by *bars*:
        1. Append to a growing sliding window.
        2. Skip warmup bars.
        3. Check stop-loss / take-profit exits.
        4. Update position mark-to-market prices.
        5. Run the feature pipeline to compute indicators.
        6. Construct a ``Candidate`` and evaluate it through the strategy pipeline.
        7. Process every actionable signal (place/close simulated orders).
        8. Record the resulting equity in the session's equity curve.

        Parameters
        ----------
        bars:
            Iterator that yields :class:`Bar` instances in chronological order.
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

        for bar in bars:
            window.append(bar.to_dict())
            session.bar_count += 1

            # Warmup phase — skip bars until the warmup window is full
            if not warmup_done:
                if config.warmup_bars > 0 and session.bar_count < config.warmup_bars:
                    continue
                warmup_done = True

            # Check stop-loss / take-profit exits and update mark-to-market
            self._check_exits(bar, session)
            for pos in session.positions.values():
                if pos.symbol == bar.symbol:
                    pos.update_price(bar.close)

            # Build window DataFrame and run feature pipeline
            window_df = self._build_window(window, config.window_size)
            try:
                features = self._pipeline.run(window_df)
            except Exception as exc:
                logger.warning("FeaturePipeline failed at bar %d: %s", session.bar_count, exc)
                features = window_df

            # Construct candidate and evaluate through strategy pipeline
            candidate = Candidate(symbol=bar.symbol, score=50.0, reasons=["paper"])
            signals = self._strategy.evaluate_single(candidate, features)

            # Process every actionable signal
            for signal in signals:
                signals_all.append(signal)
                self._process_signal(signal, bar, session)

            # Record equity after all signals for this bar have been processed
            equity = session.total_equity
            session.equity_curve.append((bar.timestamp, equity))
            if equity > session.peak_equity:
                session.peak_equity = equity

        return signals_all

    def _run_single(self, df: pd.DataFrame, symbol: str, ts_col: str) -> PaperResult:
        """Process a single symbol's data bar-by-bar."""
        config = self._config
        session = PaperSession(capital=config.initial_capital)
        session.peak_equity = config.initial_capital
        session.equity_curve.append((df[ts_col].iloc[0], config.initial_capital))

        signals_all = self._process_bar_stream(self._iter_bars(df, symbol, ts_col), session)

        # Close any open positions at end
        if not df.empty:
            last_row = df.iloc[-1]
            last_bar = Bar(
                symbol=symbol,
                timestamp=last_row[ts_col],
                open=float(last_row.get("open", 0)),
                high=float(last_row.get("high", 0)),
                low=float(last_row.get("low", 0)),
                close=float(last_row.get("close", 0)),
                volume=float(last_row.get("volume", 0)),
            )
            for sym in list(session.positions.keys()):
                self._close_position(
                    sym,
                    last_bar.close,
                    last_bar.timestamp,
                    session,
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

        symbols = df["symbol"].unique()
        all_signals: list[Signal] = []

        for sym in symbols:
            sym_df = df[df["symbol"] == sym].sort_values(ts_col).reset_index(drop=True)
            signals = self._process_bar_stream(self._iter_bars(sym_df, sym, ts_col), session)
            all_signals.extend(signals)

        # Close remaining positions using the last symbol's last bar
        last_sym = symbols[-1]
        last_row = df[df["symbol"] == last_sym].iloc[-1]
        last_bar = Bar(
            symbol=str(last_sym),
            timestamp=last_row[ts_col],
            open=float(last_row.get("open", 0)),
            high=float(last_row.get("high", 0)),
            low=float(last_row.get("low", 0)),
            close=float(last_row.get("close", 0)),
            volume=float(last_row.get("volume", 0)),
        )
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
        """Process a signal through OMS for backtest-live parity.

        Requires trading_context (or oms_adapter) passed at construction time.
        """
        if not signal.is_actionable:
            return

        self._process_signal_via_oms(signal, bar, session)

    def _process_signal_via_oms(self, signal: Signal, bar: Bar, session: PaperSession) -> None:
        """Route paper signals through OMS for parity with live/replay."""
        config = self._config
        if signal.is_buy and bar.symbol not in session.positions:
            if session.position_count >= config.max_positions:
                return
            # REF-4: float → Decimal daily-loss gate (domain policy helper).
            if config.max_daily_loss_pct > 0:
                from domain.risk.policy import check_paper_daily_loss

                loss_check = check_paper_daily_loss(
                    session.daily_pnl,
                    session.total_equity,
                    config.max_daily_loss_pct,
                )
                if not loss_check.approved:
                    logger.info(
                        "paper_daily_loss_blocked",
                        extra={"reason": loss_check.reason, "symbol": bar.symbol},
                    )
                    return
            price = _apply_slippage(Decimal(str(bar.close)), side="BUY", slippage_pct=config.slippage_pct)
            qty = compute_order_quantity(
                equity=session.capital,
                price=float(price),
                max_position_pct=config.max_position_pct,
            )
            if qty <= 0:
                return
            order_id = self._oms_adapter.open_long(
                symbol=bar.symbol,
                exchange="NSE",
                quantity=qty,
                price=price,
                timestamp=bar.timestamp,
                strategy=signal.strategy,
                reasons=list(signal.reasons),
            )
            if order_id:
                cost = float(price) * qty + config.commission_flat
                session.capital -= cost
                session.positions[bar.symbol] = PaperPosition(
                    symbol=bar.symbol,
                    side=PositionSide.LONG,
                    entry_price=float(price),
                    quantity=qty,
                    entry_time=bar.timestamp,
                    current_price=bar.close,
                    stop_loss=signal.stop_loss,
                    take_profit=signal.target,
                    strategy=signal.strategy,
                )
        elif signal.is_sell and bar.symbol in session.positions:
            pos = session.positions[bar.symbol]
            if pos.side != PositionSide.LONG:
                return
            price = _apply_slippage(Decimal(str(bar.close)), side="SELL", slippage_pct=config.slippage_pct)
            order_id = self._oms_adapter.close_long(
                symbol=bar.symbol,
                exchange="NSE",
                quantity=pos.quantity,
                price=price,
                timestamp=bar.timestamp,
                strategy=signal.strategy,
                reasons=list(signal.reasons),
            )
            if order_id:
                proceeds = float(price) * pos.quantity - config.commission_flat
                session.capital += proceeds
                del session.positions[bar.symbol]

    def _close_position(
        self,
        symbol: str,
        price: float,
        timestamp: datetime,
        session: PaperSession,
        reason: str,
    ) -> None:
        """Close a position through OMS for backtest-live parity."""
        if symbol not in session.positions:
            return

        pos = session.positions[symbol]

        # Route through OMS adapter (required for backtest-live parity)
        dec_price = Decimal(str(price))
        order_id = self._oms_adapter.close_long(
            symbol=symbol,
            exchange="NSE",
            quantity=pos.quantity,
            price=dec_price,
            timestamp=timestamp,
            strategy=pos.strategy,
            reasons=[reason],
        )

        if order_id is None:
            return  # OMS rejected the close

        # Calculate exit price with slippage
        config = self._config
        if pos.side == PositionSide.LONG:
            exit_price = float(_apply_slippage(dec_price, side="SELL", slippage_pct=config.slippage_pct))
        else:
            exit_price = float(_apply_slippage(dec_price, side="BUY", slippage_pct=config.slippage_pct))

        # Calculate P&L
        if pos.side == PositionSide.LONG:
            pnl = (exit_price - pos.entry_price) * pos.quantity
        else:
            pnl = (pos.entry_price - exit_price) * pos.quantity

        pnl_pct = ((exit_price / pos.entry_price) - 1) * 100 if pos.entry_price > 0 else 0.0
        if pos.side == PositionSide.SHORT:
            pnl_pct = -pnl_pct

        # Calculate commission
        exit_value = exit_price * pos.quantity
        commission = max(exit_value * config.commission_pct, config.commission_flat)
        slippage_cost = pos.quantity * float(dec_price) * (config.slippage_pct / 100)

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
                price=float(dec_price),
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
        if pos.stop_loss is not None and (
            (pos.side == PositionSide.LONG and bar.low <= pos.stop_loss)
            or (pos.side == PositionSide.SHORT and bar.high >= pos.stop_loss)
        ):
            self._close_position(bar.symbol, pos.stop_loss, bar.timestamp, session, "Stop-loss hit")
            return

        # Take-profit check
        if pos.take_profit is not None and (
            (pos.side == PositionSide.LONG and bar.high >= pos.take_profit)
            or (pos.side == PositionSide.SHORT and bar.low <= pos.take_profit)
        ):
            self._close_position(
                bar.symbol, pos.take_profit, bar.timestamp, session, "Take-profit hit"
            )
            return

    # -----------------------------------------------------------------------
    # Helpers
    # -----------------------------------------------------------------------

    @staticmethod
    def _iter_bars(df: pd.DataFrame, symbol: str, ts_col: str) -> Generator[Bar, None, None]:
        """Yield :class:`Bar` instances from a DataFrame in row order.

        Extracted from the old ``_bar_generator`` closures in ``_run_single``
        and ``_run_multi_symbol`` to avoid re-defining the closure on every
        iteration of the caller's loop.
        """
        for idx in range(len(df)):
            row = df.iloc[idx]
            yield Bar(
                symbol=symbol,
                timestamp=row[ts_col],
                open=float(row.get("open", 0)),
                high=float(row.get("high", 0)),
                low=float(row.get("low", 0)),
                close=float(row.get("close", 0)),
                volume=float(row.get("volume", 0)),
            )

    def _build_window(self, window: list[dict], window_size: int) -> pd.DataFrame:
        """Build a DataFrame from the window, optionally limiting size."""
        if window_size > 0:
            window = window[-window_size:]
        return pd.DataFrame(window)
