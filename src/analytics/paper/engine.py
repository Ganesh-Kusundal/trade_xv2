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
    PaperResult,
    PaperSession,
    PaperTrade,
    PositionSide,
)
from analytics.pipeline.errors import FeaturePipelineError
from analytics.pipeline.pipeline import FeaturePipeline
from domain.candles.historical import HistoricalBar
from analytics.scanner.models import Candidate
from analytics.strategy.models import Signal
from domain import Side
from domain.entities import Trade
from domain.simulation_position_meta import PositionMeta
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

        # Check stop-loss / take-profit on existing positions
        self._check_exits(bar, session)

        if session.has_position(bar.symbol):
            session.mark_symbol(bar.symbol, bar.close)

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

        features = self._run_features(window_df, session, self._config)
        if features is None:
            return []

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
        bars: Iterator[HistoricalBar],
        session: PaperSession,
    ) -> list[Signal]:
        """Shared bar-processing loop — extracted from ``_run_single`` and
        ``_run_multi_symbol`` (REF-002 DRY remediation).

        For each ``HistoricalBar`` yielded by *bars*:
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
            if session.has_position(bar.symbol):
                session.mark_symbol(bar.symbol, bar.close)

            # Build window DataFrame and run feature pipeline
            window_df = self._build_window(window, config.window_size)
            features = self._run_features(window_df, session, config)
            if features is None:
                equity = session.total_equity
                session.equity_curve.append((bar.timestamp, equity))
                if equity > session.peak_equity:
                    session.peak_equity = equity
                continue

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

        merged = df.sort_values(ts_col).reset_index(drop=True)
        if not merged.empty:
            session.equity_curve.append((merged[ts_col].iloc[0], config.initial_capital))

        all_signals = self._process_bar_stream(self._iter_bars(merged, "", ts_col), session)

        # Close remaining positions at each symbol's last bar price
        if not merged.empty:
            last_rows = merged.groupby("symbol", sort=False).last()
            for sym in list(session.open_symbols()):
                if sym not in last_rows.index:
                    continue
                row = last_rows.loc[sym]
                self._close_position(
                    sym,
                    float(row["close"]),
                    row[ts_col],
                    session,
                    "End of paper trading",
                )

        return PaperResult(
            session=session,
            config=config,
            bars_processed=session.bar_count,
            signals_generated=len(all_signals),
        )

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

    # -----------------------------------------------------------------------
    # Signal processing
    # -----------------------------------------------------------------------

    def _process_signal(self, signal: Signal, bar: HistoricalBar, session: PaperSession) -> None:
        """Process a signal through OMS for backtest-live parity.

        Requires trading_context (or oms_adapter) passed at construction time.
        """
        if not signal.is_actionable:
            return

        self._process_signal_via_oms(signal, bar, session)

    def _process_signal_via_oms(self, signal: Signal, bar: HistoricalBar, session: PaperSession) -> None:
        """Route paper signals through OMS for parity with live/replay."""
        config = self._config
        if signal.is_buy and not session.has_position(bar.symbol):
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
                self._record_session_fill(
                    session,
                    order_id=order_id,
                    symbol=bar.symbol,
                    exchange="NSE",
                    side=Side.BUY,
                    quantity=qty,
                    price=float(price),
                    timestamp=bar.timestamp,
                    trade_tag="open",
                )
                session.mark_symbol(bar.symbol, bar.close)
                session.position_meta[bar.symbol] = PositionMeta(
                    entry_time=bar.timestamp,
                    stop_loss=signal.stop_loss,
                    target=signal.target,
                    strategy=signal.strategy,
                )
        elif signal.is_sell and session.has_position(bar.symbol):
            domain_pos = session._domain_position(bar.symbol)
            if domain_pos is None or domain_pos.quantity <= 0:
                return
            qty = domain_pos.quantity
            entry_price = float(domain_pos.avg_price)
            price = _apply_slippage(Decimal(str(bar.close)), side="SELL", slippage_pct=config.slippage_pct)
            order_id = self._oms_adapter.close_long(
                symbol=bar.symbol,
                exchange="NSE",
                quantity=qty,
                price=price,
                timestamp=bar.timestamp,
                strategy=signal.strategy,
                reasons=list(signal.reasons),
            )
            if order_id:
                proceeds = float(price) * qty - config.commission_flat
                session.capital += proceeds
                simple_pnl = (float(price) - entry_price) * qty - config.commission_flat
                session.daily_pnl += simple_pnl
                self._record_session_fill(
                    session,
                    order_id=order_id,
                    symbol=bar.symbol,
                    exchange="NSE",
                    side=Side.SELL,
                    quantity=qty,
                    price=float(price),
                    timestamp=bar.timestamp,
                    trade_tag="close",
                )
                session.clear_position(bar.symbol)

    def _close_position(
        self,
        symbol: str,
        price: float,
        timestamp: datetime,
        session: PaperSession,
        reason: str,
    ) -> None:
        """Close a position through OMS for backtest-live parity."""
        view = session._to_paper_position(symbol)
        if view is None:
            return

        dec_price = Decimal(str(price))
        order_id = self._oms_adapter.close_long(
            symbol=symbol,
            exchange="NSE",
            quantity=view.quantity,
            price=dec_price,
            timestamp=timestamp,
            strategy=view.strategy,
            reasons=[reason],
        )

        if order_id is None:
            return

        config = self._config
        if view.side == PositionSide.LONG:
            exit_price = float(_apply_slippage(dec_price, side="SELL", slippage_pct=config.slippage_pct))
            close_side = Side.SELL
        else:
            exit_price = float(_apply_slippage(dec_price, side="BUY", slippage_pct=config.slippage_pct))
            close_side = Side.BUY

        if view.side == PositionSide.LONG:
            pnl = (exit_price - view.entry_price) * view.quantity
        else:
            pnl = (view.entry_price - exit_price) * view.quantity

        pnl_pct = ((exit_price / view.entry_price) - 1) * 100 if view.entry_price > 0 else 0.0
        if view.side == PositionSide.SHORT:
            pnl_pct = -pnl_pct

        exit_value = exit_price * view.quantity
        commission = max(exit_value * config.commission_pct, config.commission_flat)
        slippage_cost = view.quantity * float(dec_price) * (config.slippage_pct / 100)
        net_pnl = pnl - commission
        session.daily_pnl += net_pnl
        session.capital += view.quantity * view.entry_price + net_pnl

        session.trades.append(
            PaperTrade(
                symbol=symbol,
                side=OrderSide.BUY if view.side == PositionSide.LONG else OrderSide.SELL,
                entry_price=view.entry_price,
                exit_price=exit_price,
                quantity=view.quantity,
                entry_time=view.entry_time,
                exit_time=timestamp,
                pnl=net_pnl,
                pnl_pct=pnl_pct,
                commission=commission,
                slippage_cost=slippage_cost,
                strategy=view.strategy,
                reasons=[reason],
            )
        )

        session.orders.append(
            PaperOrder(
                order_id=f"P-{_gen_id()}",
                symbol=symbol,
                side=OrderSide.SELL if view.side == PositionSide.LONG else OrderSide.BUY,
                quantity=view.quantity,
                price=float(dec_price),
                order_time=timestamp,
                status=OrderStatus.FILLED,
                fill_price=exit_price,
                fill_time=timestamp,
                commission=commission,
                slippage=slippage_cost,
                strategy=view.strategy,
                reasons=[reason],
            )
        )

        self._record_session_fill(
            session,
            order_id=order_id,
            symbol=symbol,
            exchange="NSE",
            side=close_side,
            quantity=view.quantity,
            price=exit_price,
            timestamp=timestamp,
            trade_tag="close",
        )
        session.clear_position(symbol)

    def _check_exits(self, bar: HistoricalBar, session: PaperSession) -> None:
        """Check stop-loss and take-profit exits for all positions."""
        if not session.has_position(bar.symbol):
            return

        view = session._to_paper_position(bar.symbol)
        meta = session.position_meta.get(bar.symbol)
        if view is None:
            return

        stop_loss = meta.stop_loss if meta else view.stop_loss
        take_profit = meta.take_profit if meta else view.take_profit

        if stop_loss is not None and (
            (view.side == PositionSide.LONG and bar.low <= stop_loss)
            or (view.side == PositionSide.SHORT and bar.high >= stop_loss)
        ):
            self._close_position(bar.symbol, stop_loss, bar.timestamp, session, "Stop-loss hit")
            return

        if take_profit is not None and (
            (view.side == PositionSide.LONG and bar.high >= take_profit)
            or (view.side == PositionSide.SHORT and bar.low <= take_profit)
        ):
            self._close_position(
                bar.symbol, take_profit, bar.timestamp, session, "Take-profit hit"
            )
            return

    # -----------------------------------------------------------------------
    # Helpers
    # -----------------------------------------------------------------------

    @staticmethod
    def _iter_bars(df: pd.DataFrame, symbol: str, ts_col: str) -> Generator[HistoricalBar, None, None]:
        """Yield :class:`HistoricalBar` instances from a DataFrame in row order.

        Extracted from the old ``_bar_generator`` closures in ``_run_single``
        and ``_run_multi_symbol`` to avoid re-defining the closure on every
        iteration of the caller's loop.
        """
        for idx in range(len(df)):
            row = df.iloc[idx]
            sym = str(row["symbol"]) if "symbol" in df.columns else symbol
            yield HistoricalBar.from_replay(
                symbol=sym,
                timestamp=row[ts_col],
                open=float(row.get("open", 0)),
                high=float(row.get("high", 0)),
                low=float(row.get("low", 0)),
                close=float(row.get("close", 0)),
                volume=float(row.get("volume", 0)),
            )

    def _run_features(
        self,
        window_df: pd.DataFrame,
        session: PaperSession,
        config: PaperConfig,
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

    def _build_window(self, window: list[dict], window_size: int) -> pd.DataFrame:
        """Build a DataFrame from the window, optionally limiting size."""
        if window_size > 0:
            window = window[-window_size:]
        return pd.DataFrame(window)
