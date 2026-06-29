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
    1. Receive Bar (OHLCV)
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
    from cli.services.compose import build_runtime
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

from analytics.pipeline.pipeline import FeaturePipeline
from analytics.replay.models import (
    Bar,
    FillModel,
    ReplayConfig,
    ReplayResult,
    ReplaySession,
    SimulatedPosition,
    SimulatedTrade,
)
from analytics.scanner.models import Candidate
from analytics.strategy.models import Signal
from analytics.strategy.pipeline import StrategyPipeline
from domain.execution import compute_order_quantity
from domain.ports.oms_backtest_adapter import OmsBacktestAdapterPort
from domain.runtime_hooks import create_oms_backtest_adapter
from domain.symbols import normalize_symbol
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
    ) -> None:
        self._pipeline = pipeline or FeaturePipeline()
        self._strategy = strategy_pipeline or StrategyPipeline()
        self._config = config or ReplayConfig()
        self._event_bus = event_bus
        self._trading_context = trading_context
        self._execution_adapter = execution_adapter
        self._portfolio_tracker = portfolio_tracker

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
        else:
            raise TypeError(
                "ReplayEngine requires trading_context (or oms_adapter) for order execution. "
                "Pass a TradingContext instance from your composition root."
            )

    def _compute_commission(self, notional: float, side: str) -> float:
        """Compute commission based on the configured model.

        Delegates to domain.trading_costs.compute_commission (single source of truth).
        """
        cfg = self._config
        return compute_commission(
            notional, side,
            model=cfg.commission_model,
            flat_fee=cfg.commission_flat,
            fees=cfg.indian_market_fees,
        )

    def _compute_slippage_pct(self, bar_volume: float) -> float:
        """Compute effective slippage percentage based on the configured model.

        Delegates to domain.trading_costs.compute_slippage_pct (single source of truth).
        """
        cfg = self._config
        return compute_slippage_pct(
            cfg.slippage_model,
            cfg.slippage_pct,
            bar_volume,
            cfg.avg_volume,
        )

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

    def _run_single(self, df: pd.DataFrame, symbol: str, ts_col: str) -> ReplayResult:
        """Process a single symbol's data bar-by-bar."""
        config = self._config
        session = ReplaySession(capital=config.initial_capital)
        session.peak_equity = config.initial_capital
        session.equity_curve.append((df[ts_col].iloc[0], config.initial_capital))

        # Pre-allocated numpy arrays as ring buffer.
        # pd.DataFrame(list_of_dicts) is replaced by pd.DataFrame(dict_of_arrays)
        # which is 10-20x faster because numpy arrays are columnar and don't require
        # per-row dict unpacking. For window_size=200 with 100K bars, the numpy
        # shift+append is O(window_size) in C, vs O(window_size) dict construction.
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
        else:
            # Unlimited window — fall back to deque (no pre-allocation possible)
            _window_data = deque()

        warmup_done = False
        pending_signals: list[tuple[Signal, Bar]] = []

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

            # Process pending signals from previous bar using this bar's open
            if pending_signals:
                for sig, sig_bar in pending_signals:
                    self._process_signal(sig, bar, session, config, fill_price=bar.open)
                    if config.publish_events and self._event_bus is not None:
                        self._publish_signal(sig)
                pending_signals.clear()

            # Write bar into pre-allocated numpy arrays or deque
            if window_size > 0:
                if _filled < window_size:
                    # Growing phase: write at the end
                    _widx = _filled
                    _arr_open[_widx] = bar.open
                    _arr_high[_widx] = bar.high
                    _arr_low[_widx] = bar.low
                    _arr_close[_widx] = bar.close
                    _arr_volume[_widx] = bar.volume
                    _arr_symbol[_widx] = bar.symbol
                    _arr_timestamp[_widx] = bar.timestamp
                    _filled += 1
                else:
                    # Full: shift left by 1 (numpy-level C memmove) and append
                    _arr_open[:-1] = _arr_open[1:]
                    _arr_high[:-1] = _arr_high[1:]
                    _arr_low[:-1] = _arr_low[1:]
                    _arr_close[:-1] = _arr_close[1:]
                    _arr_volume[:-1] = _arr_volume[1:]
                    _arr_symbol[:-1] = _arr_symbol[1:]
                    _arr_timestamp[:-1] = _arr_timestamp[1:]
                    _arr_open[-1] = bar.open
                    _arr_high[-1] = bar.high
                    _arr_low[-1] = bar.low
                    _arr_close[-1] = bar.close
                    _arr_volume[-1] = bar.volume
                    _arr_symbol[-1] = bar.symbol
                    _arr_timestamp[-1] = bar.timestamp
            else:
                _window_data.append(bar.to_dict())

            session.bar_count += 1

            # Warmup phase
            if not warmup_done:
                if config.warmup_bars > 0 and session.bar_count < config.warmup_bars:
                    continue
                warmup_done = True

            # Build window DataFrame from numpy arrays (not list-of-dicts).
            # pd.DataFrame(dict_of_arrays) is ~10-20x faster than pd.DataFrame(list_of_dicts)
            # because numpy arrays are already columnar — no per-row dict unpacking needed.
            if window_size > 0:
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
                window_df = pd.DataFrame(_window_data)

            # Run FeaturePipeline
            try:
                features = self._pipeline.run(window_df)
            except Exception as exc:
                logger.warning("FeaturePipeline failed at bar %d: %s", session.bar_count, exc)
                features = window_df

            # Construct Candidate
            candidate = Candidate(symbol=symbol, score=50.0, reasons=["replay"])

            # Check intra-bar stop-loss/target BEFORE processing signals
            if session.position is not None:
                pos = session.position
                hit_stop = pos.stop_loss is not None and bar.low <= pos.stop_loss
                hit_target = pos.target is not None and bar.high >= pos.target

                if hit_stop or hit_target:
                    reason = "Stop-loss hit" if hit_stop else "Target hit"
                    exit_price = pos.stop_loss if hit_stop else pos.target
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

            # Update equity
            equity = session.current_equity
            session.equity_curve.append((bar_ts, equity))
            if equity > session.peak_equity:
                session.peak_equity = equity

        # Close any open position at end (bar holds the last loop iteration's bar)
        if session.position is not None:
            self._close_position(session, bar, "End of replay")

        # Process any remaining pending signals (next-bar-open with no next bar)
        if pending_signals:
            for sig, sig_bar in pending_signals:
                self._process_signal(sig, bar, session, config, fill_price=bar.open)
                if config.publish_events and self._event_bus is not None:
                    self._publish_signal(sig)

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
        for _sym, s in sessions_per_symbol.items():
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

    def _build_window(self, window_data, window_size: int) -> pd.DataFrame:
        """Build a DataFrame from the window data (deprecated by REF-022 ring buffer).

        Retained for backward compatibility with external callers.
        """
        # If it's a deque with maxlen, it's already bounded
        # If it's a list and window_size > 0, slice it
        if isinstance(window_data, list) and window_size > 0:
            window_data = window_data[-window_size:]
        return pd.DataFrame(window_data)

    def _process_signal(
        self,
        signal: Signal,
        bar: Bar,
        session: ReplaySession,
        config: ReplayConfig,
        fill_price: float | None = None,
    ) -> None:
        """Process a signal through OMS for backtest-live parity.

        Requires ``trading_context`` (or ``oms_adapter``) passed at construction time.
        """
        if not signal.is_actionable:
            return

        self._process_signal_via_oms(signal, bar, session, config, fill_price=fill_price)

    def _process_signal_via_oms(
        self,
        signal: Signal,
        bar: Bar,
        session: ReplaySession,
        config: ReplayConfig,
        fill_price: float | None = None,
    ) -> None:
        """Route signal through OMS for backtest-live parity (P0-2).

        Opens/closes positions via :class:`OmsBacktestAdapter`, which consults
        the same risk gates, idempotency ledger, and event bus as live trading.
        """
        if signal.is_buy and session.position is None:
            # Open long via OMS
            base_price = fill_price if fill_price is not None else bar.close
            slippage_pct = self._compute_slippage_pct(bar.volume)
            price = Decimal(str(base_price * (1 + slippage_pct / 100)))
            qty = compute_order_quantity(
                equity=session.capital,
                price=float(price),
                max_position_pct=config.max_position_pct,
            )

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
                    # Update session state to track position
                    notional = float(price) * qty
                    commission = self._compute_commission(notional, "BUY")
                    cost = notional + commission
                    session.capital -= cost
                    session.position = SimulatedPosition(
                        symbol=bar.symbol,
                        side="BUY",
                        entry_price=float(price),
                        quantity=qty,
                        entry_time=bar.timestamp,
                        stop_loss=signal.stop_loss,
                        target=signal.target,
                        strategy=signal.strategy,
                    )
                    # Sync from PortfolioTracker if available
                    self._sync_session_from_tracker(session, bar.timestamp, bar.symbol)

        elif signal.is_sell and session.position is not None:
            # Close long via OMS
            base_price = fill_price if fill_price is not None else bar.close
            slippage_pct = self._compute_slippage_pct(bar.volume)
            price = Decimal(str(base_price * (1 - slippage_pct / 100)))
            order_id = self._oms_adapter.close_long(
                symbol=bar.symbol,
                exchange="NSE",
                quantity=session.position.quantity,
                price=price,
                timestamp=bar.timestamp,
                strategy=signal.strategy,
                reasons=["replay_signal"],
            )
            if order_id:
                # Update session state
                notional = float(price) * session.position.quantity
                commission = self._compute_commission(notional, "SELL")
                proceeds = notional - commission
                session.capital += proceeds
                session.position = None
                # Sync from PortfolioTracker if available
                self._sync_session_from_tracker(session, bar.timestamp, bar.symbol)

    def _close_position(self, session: ReplaySession, bar: Bar, reason: str) -> None:
        """Close the current position through OMS and record the trade."""
        pos = session.position
        if pos is None:
            return

        # Route through OMS for backtest-live parity (P0-2)
        slippage_pct = self._compute_slippage_pct(bar.volume)
        price = Decimal(str(bar.close * (1 - slippage_pct / 100)))
        order_id = self._oms_adapter.close_long(
            symbol=pos.symbol,
            exchange="NSE",
            quantity=pos.quantity,
            price=price,
            timestamp=bar.timestamp,
            strategy=pos.strategy,
            reasons=[reason],
        )
        if order_id is None:
            return  # OMS rejected the close

        exit_price = float(price)
        notional = exit_price * pos.quantity
        commission = self._compute_commission(notional, "SELL")
        exit_price_d = Decimal(str(exit_price))
        entry_price_d = Decimal(str(pos.entry_price))
        commission_d = Decimal(str(commission))
        pnl = (exit_price_d - entry_price_d) * pos.quantity - commission_d
        pnl_pct = float(((exit_price_d / entry_price_d) - 1) * 100) if entry_price_d > 0 else 0.0

        session.capital += notional - commission
        session.trades.append(
            SimulatedTrade(
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
            )
        )
        session.position = None

    def _close_position_at_price(
        self,
        session: ReplaySession,
        bar: Bar,
        exit_price: float,
        reason: str,
    ) -> None:
        """Close position at specific price through OMS (for stop-loss/target triggers).

        P2-3: This method is called when intra-bar price action hits a position's
        stop-loss or target level. Routes through OMS for backtest-live parity.

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
        pos = session.position
        if pos is None:
            return

        # Route through OMS for backtest-live parity (P0-2)
        price = Decimal(str(exit_price))
        order_id = self._oms_adapter.close_long(
            symbol=pos.symbol,
            exchange="NSE",
            quantity=pos.quantity,
            price=price,
            timestamp=bar.timestamp,
            strategy=pos.strategy,
            reasons=[reason],
        )
        if order_id is None:
            return  # OMS rejected the close

        # Update session state
        notional = exit_price * pos.quantity
        commission = self._compute_commission(notional, "SELL")
        exit_price_d = Decimal(str(exit_price))
        entry_price_d = Decimal(str(pos.entry_price))
        commission_d = Decimal(str(commission))
        pnl = (exit_price_d - entry_price_d) * pos.quantity - commission_d
        pnl_pct = float(((exit_price_d / entry_price_d) - 1) * 100) if entry_price_d > 0 else 0.0

        session.capital += notional - commission
        session.trades.append(
            SimulatedTrade(
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
            )
        )
        session.position = None

    def _sync_session_from_tracker(
        self,
        session: ReplaySession,
        bar_timestamp: datetime | None = None,
        symbol: str | None = None,
    ) -> None:
        """Sync session state from PortfolioTracker.

        Reads capital and position state from the PortfolioTracker
        (backed by the production OMS) and updates the session shadow
        state to match, eliminating drift between the two.

        Parameters
        ----------
        session:
            Current replay session to update.
        bar_timestamp:
            Timestamp of the current bar for accurate entry_time.
            Falls back to UTC now if *None*.
        symbol:
            Symbol being replayed — used to filter positions so the
            correct instrument is matched when the tracker holds
            multiple positions.
        """
        if self._portfolio_tracker is None:
            return

        session.capital = float(self._portfolio_tracker.get_capital())

        positions = self._portfolio_tracker.get_positions()
        if symbol is not None:
            positions = [p for p in positions if p.symbol.upper() == normalize_symbol(symbol)]

        if positions:
            pos = positions[0]
            entry_time = bar_timestamp if bar_timestamp is not None else datetime.now(timezone.utc)
            session.position = SimulatedPosition(
                symbol=pos.symbol,
                side="BUY" if pos.quantity > 0 else "SELL",
                entry_price=float(pos.avg_price),
                quantity=abs(pos.quantity),
                entry_time=entry_time,
            )
        else:
            session.position = None

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
