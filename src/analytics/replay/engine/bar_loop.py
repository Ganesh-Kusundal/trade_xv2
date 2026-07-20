"""Bar-by-bar replay loop logic for ReplayEngine.

Extracted from engine.py to reduce god-object size. Contains the single-symbol
and multi-symbol replay loops that process OHLCV data bar-by-bar through the
feature and strategy pipelines.
"""

from __future__ import annotations

import logging
from collections import deque

import numpy as np
import pandas as pd

from analytics.replay.event_publishing import (
    publish_scheduled_events as _publish_scheduled,
)
from analytics.replay.event_publishing import (
    publish_signal as _publish_sig,
)
from analytics.replay.models import (
    FillModel,
    ReplayResult,
    ReplaySession,
)
from analytics.replay.window import (
    append_bar as _append_bar,
)
from analytics.replay.window import (
    new_window_state as _new_window_state_fn,
)
from analytics.replay.window import (
    to_dataframe as _to_dataframe,
)
from analytics.scanner.models import Candidate
from analytics.strategy.models import Signal
from domain.candles.historical import HistoricalBar

logger = logging.getLogger(__name__)


def run_single(engine, df: pd.DataFrame, symbol: str, ts_col: str) -> ReplayResult:
    """Process a single symbol's data bar-by-bar."""
    config = engine._config
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
        if engine._event_schedule and engine._event_bus is not None:
            _publish_scheduled(engine._event_bus, engine._event_schedule, bar_ts)

        # Process pending signals from previous bar using this bar's open
        if pending_signals:
            for sig, _sig_bar in pending_signals:
                engine._process_signal(sig, bar, session, config, fill_price=bar.open)
                if config.publish_events and engine._event_bus is not None:
                    _publish_sig(engine._event_bus, sig)
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
                window_df = pd.DataFrame(
                    {
                        "open": _arr_open[:_filled],
                        "high": _arr_high[:_filled],
                        "low": _arr_low[:_filled],
                        "close": _arr_close[:_filled],
                        "volume": _arr_volume[:_filled],
                        "symbol": _arr_symbol[:_filled],
                        "timestamp": _arr_timestamp[:_filled],
                    }
                )
            else:
                # Circular buffer full — reorder from oldest to newest
                _idx = np.arange(_head - window_size, _head) % window_size
                window_df = pd.DataFrame(
                    {
                        "open": _arr_open[_idx],
                        "high": _arr_high[_idx],
                        "low": _arr_low[_idx],
                        "close": _arr_close[_idx],
                        "volume": _arr_volume[_idx],
                        "symbol": _arr_symbol[_idx],
                        "timestamp": _arr_timestamp[_idx],
                    }
                )
        else:
            window_df = pd.DataFrame(_window_data)

        features = engine._run_features(window_df, session, config)
        if features is None:
            equity = session.current_equity
            session.equity_curve.append((bar_ts, equity))
            if equity > session.peak_equity:
                session.peak_equity = equity
            engine._feed_parity_risk_state(session, bar)
            continue

        candidate = Candidate(symbol=symbol, score=50.0, reasons=["replay"])

        if session.has_position(bar.symbol):
            meta = session.position_meta.get(bar.symbol)
            hit_stop = meta is not None and meta.stop_loss is not None and bar.low <= meta.stop_loss
            hit_target = meta is not None and meta.target is not None and bar.high >= meta.target

            if hit_stop or hit_target:
                reason = "Stop-loss hit" if hit_stop else "Target hit"
                exit_price = meta.stop_loss if hit_stop else meta.target
                engine._close_position_at_price(session, bar, exit_price, reason)
                # Skip signal processing for this bar - position already closed
                # Update equity and continue to next bar
                equity = session.current_equity
                session.equity_curve.append((bar_ts, equity))
                if equity > session.peak_equity:
                    session.peak_equity = equity
                engine._feed_parity_risk_state(session, bar)
                continue

        # Run StrategyPipeline
        signals = engine._strategy.evaluate_single(candidate, features)
        from application.trading.signal_coordinator import coalesce_strategy_signals

        signals = coalesce_strategy_signals(signals)

        # Process signals (P0-2: routes through OMS if available)
        for signal in signals:
            session.signals.append(signal)
            if config.fill_model == FillModel.NEXT_OPEN:
                pending_signals.append((signal, bar))
            else:
                engine._process_signal(signal, bar, session, config)
                if config.publish_events and engine._event_bus is not None:
                    _publish_sig(engine._event_bus, signal)

        if session.has_position(bar.symbol):
            session.mark_symbol(bar.symbol, float(bar.close))

        # Update equity
        equity = session.current_equity
        session.equity_curve.append((bar_ts, equity))
        if equity > session.peak_equity:
            session.peak_equity = equity
        engine._feed_parity_risk_state(session, bar)

    if session.has_position(bar.symbol):
        engine._close_position(session, bar, "End of replay")
        engine._feed_parity_risk_state(session, bar)
    # Process any remaining pending signals (next-bar-open with no next bar)
    if pending_signals:
        for sig, _sig_bar in pending_signals:
            engine._process_signal(sig, bar, session, config, fill_price=bar.open)
            if config.publish_events and engine._event_bus is not None:
                _publish_sig(engine._event_bus, sig)

    return ReplayResult(
        session=session,
        config=config,
        bars_processed=session.bar_count,
        signals_generated=len(session.signals),
    )


def run_multi_symbol(engine, df: pd.DataFrame, ts_col: str) -> ReplayResult:
    """Process multiple symbols chronologically with shared capital."""
    config = engine._config
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

        if engine._event_schedule and engine._event_bus is not None:
            _publish_scheduled(engine._event_bus, engine._event_schedule, bar_ts)

        sym_pending = pending_signals.setdefault(symbol, [])
        if sym_pending:
            for sig, _sig_bar in sym_pending:
                engine._process_signal(sig, bar, session, config, fill_price=bar.open)
                if config.publish_events and engine._event_bus is not None:
                    _publish_sig(engine._event_bus, sig)
            sym_pending.clear()

        if symbol not in window_states:
            window_states[symbol] = _new_window_state_fn(window_size)
        _append_bar(window_states[symbol], bar)

        session.bar_count += 1
        symbol_bar_counts[symbol] = symbol_bar_counts.get(symbol, 0) + 1

        if not warmup_done.get(symbol, False):
            if config.warmup_bars > 0 and symbol_bar_counts[symbol] < config.warmup_bars:
                continue
            warmup_done[symbol] = True

        window_df = _to_dataframe(window_states[symbol])
        features = engine._run_features(window_df, session, config)
        if features is None:
            equity = session.current_equity
            session.equity_curve.append((bar_ts, equity))
            if equity > session.peak_equity:
                session.peak_equity = equity
            engine._feed_parity_risk_state(session, bar)
            continue

        candidate = Candidate(symbol=symbol, score=50.0, reasons=["replay"])

        if session.has_position(bar.symbol):
            meta = session.position_meta.get(bar.symbol)
            hit_stop = meta is not None and meta.stop_loss is not None and bar.low <= meta.stop_loss
            hit_target = meta is not None and meta.target is not None and bar.high >= meta.target

            if hit_stop or hit_target:
                reason = "Stop-loss hit" if hit_stop else "Target hit"
                exit_price = meta.stop_loss if hit_stop else meta.target
                engine._close_position_at_price(session, bar, exit_price, reason)
                equity = session.current_equity
                session.equity_curve.append((bar_ts, equity))
                if equity > session.peak_equity:
                    session.peak_equity = equity
                engine._feed_parity_risk_state(session, bar)
                continue

        signals = engine._strategy.evaluate_single(candidate, features)
        from application.trading.signal_coordinator import coalesce_strategy_signals

        signals = coalesce_strategy_signals(signals)
        for signal in signals:
            session.signals.append(signal)
            if config.fill_model == FillModel.NEXT_OPEN:
                sym_pending.append((signal, bar))
            else:
                engine._process_signal(signal, bar, session, config)
                if config.publish_events and engine._event_bus is not None:
                    _publish_sig(engine._event_bus, signal)

        if session.has_position(bar.symbol):
            session.mark_symbol(bar.symbol, float(bar.close))

        equity = session.current_equity
        session.equity_curve.append((bar_ts, equity))
        if equity > session.peak_equity:
            session.peak_equity = equity
        engine._feed_parity_risk_state(session, bar)

    for symbol, bar in last_bars.items():
        if session.has_position(symbol):
            engine._close_position(session, bar, "End of replay")
            engine._feed_parity_risk_state(session, bar)
    for symbol, sym_pending in pending_signals.items():
        if not sym_pending:
            continue
        bar = last_bars.get(symbol)
        if bar is None:
            continue
        for sig, _sig_bar in sym_pending:
            engine._process_signal(sig, bar, session, config, fill_price=bar.open)
            if config.publish_events and engine._event_bus is not None:
                _publish_sig(engine._event_bus, sig)

    return ReplayResult(
        session=session,
        config=config,
        bars_processed=session.bar_count,
        signals_generated=len(session.signals),
    )
