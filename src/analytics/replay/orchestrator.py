"""UnifiedReplayOrchestrator — deterministic event+bar replay.

Merges historical bar data from the datalake with persisted domain
events from the EventLog into a single time-ordered stream.  The
combined stream is replayed through the same FeaturePipeline →
StrategyPipeline → OMS stack used in live trading, then the final
state is asserted against the recorded state from the event log.

Deterministic replay guarantees
-------------------------------
1. **Single time source**: All bars and events carry timezone-aware
   timestamps. The merge sort uses (timestamp, sequence_number) as
   a composite key, guaranteeing a total order even when timestamps
   collide.

2. **No side effects**: In replay mode, the EventBus disables auto-
   persistence (no recursive writes to EventLog) and uses the
   original event timestamps instead of ``datetime.now()``.

3. **Idempotent pipelines**: FeaturePipeline and StrategyPipeline are
   pure functions of their input. Caching is disabled during replay
   to avoid stale cache hits across runs.

4. **State assertion**: After replay completes, the orchestrator
   compares the final portfolio state (equity, positions, trade
   count) against a snapshot derived from the event log. Any
   mismatch raises ``ReplayAssertionError``.

Usage::

    from analytics.replay.orchestrator import UnifiedReplayOrchestrator
    from analytics.pipeline import FeaturePipeline, RSI, ATR, SMA
    from analytics.strategy.pipeline import StrategyPipeline, MomentumStrategy

    pipeline = FeaturePipeline().add(RSI(14)).add(ATR(14)).add(SMA(20))
    strategy = StrategyPipeline(strategies=[MomentumStrategy()])

    orchestrator = UnifiedReplayOrchestrator(
        feature_pipeline=pipeline,
        strategy_pipeline=strategy,
        events_dir="data/state/events",
        data_root="data/lake",
    )
    result = orchestrator.run(
        date="2026-01-15",
        symbols=["RELIANCE", "TCS"],
        initial_capital=100_000,
    )
    print(result.summary)
    print(f"State match: {result.state_matches}")

This module is a thin facade. Responsibilities are delegated to:
- ``ReplayDataLoader``  (data loading)
- ``StreamMerger``       (stream merging)
- ``ReplayStateAssertor`` (state assertion + expected-state derivation)
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from analytics.replay.data_loader import ReplayDataLoader
from analytics.replay.models import ReplayItem, UnifiedReplayResult
from analytics.replay.state_assertor import ReplayStateAssertor
from analytics.replay.stream_merger import StreamMerger
from domain.ports.data_catalog import DEFAULT_DATA_ROOT

# Re-exported for backward compatibility (kept here so existing imports
# such as ``from analytics.replay.orchestrator import ReplayItem`` keep working).
__all__ = [
    "ReplayItem",
    "UnifiedReplayResult",
    "UnifiedReplayOrchestrator",
]

logger = logging.getLogger(__name__)


class UnifiedReplayOrchestrator:
    """Orchestrates deterministic replay of bars + events.

    The orchestrator:
    1. Loads bar data from the datalake for the target date and symbols.
    2. Loads domain events from the EventLog for the target date.
    3. Merges both into a single time-ordered stream.
    4. Drives the stream through FeaturePipeline → StrategyPipeline → OMS.
    5. Asserts final state matches a snapshot derived from the event log.

    Parameters
    ----------
    events_dir:
        Path to the event log directory.
    data_root:
        Root path for the datalake (default ``market_data``).
    timeframe:
        Candle timeframe (default ``1m``).
    """

    def __init__(
        self,
        feature_pipeline=None,
        strategy_pipeline=None,
        events_dir: str | Path | None = None,
        data_root: str = DEFAULT_DATA_ROOT,
        timeframe: str = "1m",
        initial_capital: float = 100_000.0,
        warmup_bars: int = 20,
        trading_context: Any = None,
        data_provider: Any | None = None,
        event_log: Any | None = None,
        event_bus_factory: Any | None = None,
    ) -> None:
        self._feature_pipeline = feature_pipeline
        self._strategy_pipeline = strategy_pipeline
        self._data_root = data_root
        self._timeframe = timeframe
        self._initial_capital = initial_capital
        self._warmup_bars = warmup_bars
        self._trading_context = trading_context
        self._data_provider = (
            data_provider  # Injected data provider (DataLakeGateway or ResearchAPI)
        )

        # Event log for reading persisted events — inject or create via factory
        if event_log is not None:
            self._event_log = event_log
        elif events_dir is not None:
            from infrastructure.event_log import EventLog

            self._event_log = EventLog(events_dir=events_dir)
        else:
            self._event_log = None

        # Event bus factory — inject or use default (lazy import)
        self._event_bus_factory = event_bus_factory

        # Delegated collaborators
        self._data_loader = ReplayDataLoader(
            data_provider=self._data_provider,
            event_log=self._event_log,
            data_root=self._data_root,
            timeframe=self._timeframe,
        )
        self._stream_merger = StreamMerger()
        self._state_assertor = ReplayStateAssertor()

    def run(
        self,
        date: str,
        symbols: list[str] | None = None,
        assert_state: bool = True,
    ) -> UnifiedReplayResult:
        """Run a deterministic replay for the given date.

        Parameters
        ----------
        date:
            Target date in ``YYYY-MM-DD`` format.
        symbols:
            List of symbols to replay. If None, replays all symbols
            that have data for the date.
        assert_state:
            If True (default), asserts final state matches recorded
            state from the event log.

        Returns
        -------
        UnifiedReplayResult:
            Replay output with state assertion results.
        """
        target_date = datetime.strptime(date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        day_end = target_date.replace(hour=23, minute=59, second=59, microsecond=999999)

        # Step 1: Load events from event log
        event_items = self._load_events(target_date, day_end)

        # Step 2: Load bar data
        bar_items = self._load_bars(date, symbols or [])

        if not bar_items and not event_items:
            logger.warning("No data found for %s", date)
            return UnifiedReplayResult(
                replay_result=None,
                events_replayed=0,
                bars_replayed=0,
                state_matches=False,
                state_diff={"error": "no data"},
            )

        # Step 3: Merge into single time-ordered stream
        merged = self._merge_streams(bar_items, event_items)
        logger.info(
            "Replay stream: %d bars + %d events = %d total items",
            len(bar_items),
            len(event_items),
            len(merged),
        )

        # Step 4: Build combined OHLCV DataFrame
        combined_df = self._build_combined_df(bar_items)

        # Step 5: Create EventBus in replay mode
        if self._event_bus_factory is not None:
            replay_bus = self._event_bus_factory(
                event_log=self._event_log,
                logging_enabled=False,
                replay_mode=True,
            )
        else:
            from infrastructure.event_bus.event_bus import EventBus

            replay_bus = EventBus(
                event_log=self._event_log,
                logging_enabled=False,  # Disable auto-persistence during replay
                replay_mode=True,  # P4: Deterministic replay mode
            )

        # Step 6: Run replay through engine
        # Note: ReplayEngine handles the actual bar-by-bar processing
        # This is a simplified version - full implementation would
        # integrate with existing ReplayEngine
        replay_result = self._execute_replay(combined_df, merged, replay_bus)

        # Step 7: State assertion
        state_matches = True
        state_diff: dict[str, Any] = {}
        if assert_state and event_items:
            state_matches, state_diff = self._assert_state(replay_result, event_items)

        return UnifiedReplayResult(
            replay_result=replay_result,
            events_replayed=len(event_items),
            bars_replayed=len(bar_items),
            state_matches=state_matches,
            state_diff=state_diff,
            metadata={"date": date, "symbols": symbols},
        )

    # ── Internal helpers (delegate to focused modules) ──────────────────

    def _load_bars(self, date: str, symbols: list[str]) -> list[ReplayItem]:
        """Load OHLCV bars from the datalake for the target date."""
        return self._data_loader.load_bars(date, symbols)

    def _df_to_items(self, df: pd.DataFrame, symbol: str, seq_start: int = 0) -> list[ReplayItem]:
        """Convert a DataFrame of OHLCV data to ReplayItems (vectorized)."""
        return self._data_loader.df_to_items(df, symbol, seq_start=seq_start)

    def _load_events(self, day_start: datetime, day_end: datetime) -> list[ReplayItem]:
        """Load domain events from the event log for the target day."""
        return self._data_loader.load_events(day_start, day_end)

    def _merge_streams(self, bars: list[ReplayItem], events: list[ReplayItem]) -> list[ReplayItem]:
        """Merge bars and events into a single time-ordered stream."""
        return self._stream_merger.merge(bars, events)

    def _build_combined_df(self, bar_items: list[ReplayItem]) -> pd.DataFrame:
        """Build a combined OHLCV DataFrame from bar items."""
        return self._stream_merger.build_df(bar_items)

    def _execute_replay(
        self,
        df: pd.DataFrame,
        merged_stream: list[ReplayItem],
        event_bus: Any,
    ) -> Any:
        """Execute the replay through the engine.

        P0-1 fix: Events are now interleaved with bars by timestamp instead of
        being published all at once before bar processing. The event schedule
        maps timestamps to lists of DomainEvents that are published before the
        bar at that timestamp is processed.
        """
        if df.empty:
            return None

        if self._feature_pipeline is None or self._strategy_pipeline is None:
            logger.warning("UnifiedReplayOrchestrator: pipelines not configured")
            return None

        from analytics.replay.engine import ReplayEngine
        from analytics.replay.models import ReplayConfig
        from domain.runtime_hooks import create_trading_context

        # P0-1 fix: Build event schedule from merged stream.
        # Instead of publishing ALL events before ANY bars (which broke
        # deterministic replay), we map event timestamps to their events
        # and pass this schedule to the ReplayEngine. The engine publishes
        # events in time order as it processes each bar.
        event_schedule: dict[pd.Timestamp, list] = {}
        for item in merged_stream:
            if item.kind == "event" and item.event is not None:
                evt_ts = pd.Timestamp(item.timestamp)
                if evt_ts not in event_schedule:
                    event_schedule[evt_ts] = []
                event_schedule[evt_ts].append(item.event)

        logger.info(
            "Built event schedule with %d timestamp entries from %d total events",
            len(event_schedule),
            sum(len(evts) for evts in event_schedule.values()),
        )

        tc = self._trading_context or create_trading_context(
            event_bus=event_bus,
            replay_events=False,
        )

        config = ReplayConfig(
            initial_capital=self._initial_capital,
            warmup_bars=self._warmup_bars,
        )
        engine = ReplayEngine(
            self._feature_pipeline,
            self._strategy_pipeline,
            config,
            trading_context=tc,
            event_bus=event_bus,
            event_schedule=event_schedule,
        )

        symbol = str(df["symbol"].iloc[0]) if "symbol" in df.columns and not df.empty else "REPLAY"
        return engine.run(df, symbol=symbol)

    def _assert_state(
        self,
        result: Any,
        event_items: list[ReplayItem],
    ) -> tuple[bool, dict[str, Any]]:
        """Assert replayed state matches recorded state from events.

        P0-2 fix: Strengthened state assertion to compare:
        - Trade count (from TRADE/TRADE_APPLIED events vs replay session)
        - Final equity (within tolerance for floating-point comparison)
        - Trade details (symbol, side, quantity match)
        - Position state (open/closed)
        """
        return self._state_assertor.assert_state(result, event_items)

    def _derive_expected_equity(
        self,
        event_items: list[ReplayItem],
        initial_capital: float = 100_000.0,
        *,
        commission_per_trade: float = 20.0,
        slippage_bps: float = 5.0,
    ) -> float | None:
        """Derive expected final equity including commissions/slippage (TOS-P6-006)."""
        return self._state_assertor.derive_expected_equity(
            event_items,
            initial_capital=initial_capital,
            commission_per_trade=commission_per_trade,
            slippage_bps=slippage_bps,
        )

    def _derive_expected_trades(self, event_items: list[ReplayItem]) -> list[tuple]:
        """Derive expected trade list from TRADE/TRADE_APPLIED events."""
        return self._state_assertor.derive_expected_trades(event_items)

    def _derive_expected_position_state(self, event_items: list[ReplayItem]) -> bool:
        """Derive expected position state (has open position?) from events."""
        return self._state_assertor.derive_expected_position_state(event_items)
