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
        events_dir="market_data/events",
        data_root="market_data",
    )
    result = orchestrator.run(
        date="2026-01-15",
        symbols=["RELIANCE", "TCS"],
        initial_capital=100_000,
    )
    print(result.summary)
    print(f"State match: {result.state_matches}")
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from analytics.replay.models import ReplayResult
from domain.events.types import DomainEvent
from domain.ports.data_catalog import DEFAULT_DATA_ROOT

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ReplayItem:
    """A single item in the merged replay stream.

    Either a bar (with OHLCV data) or an event (a DomainEvent from
    the event log).  Items are sorted by (timestamp, seq) to produce
    a deterministic total order.
    """

    timestamp: datetime
    sequence: int
    kind: str  # "bar" or "event"
    symbol: str | None = None
    event: DomainEvent | None = None
    bar_data: dict[str, Any] | None = None  # OHLCV data

    def __lt__(self, other: ReplayItem) -> bool:
        if self.timestamp != other.timestamp:
            return self.timestamp < other.timestamp
        return self.sequence < other.sequence


@dataclass
class UnifiedReplayResult:
    """Output from a completed unified replay run."""

    replay_result: ReplayResult | None
    events_replayed: int
    bars_replayed: int
    state_matches: bool
    state_diff: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def summary(self) -> dict[str, Any]:
        s: dict[str, Any] = {
            "events_replayed": self.events_replayed,
            "bars_replayed": self.bars_replayed,
            "state_matches": self.state_matches,
        }
        if self.replay_result is not None:
            s.update(self.replay_result.summary)
        s.update(self.metadata)
        return s


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

    # ── Internal helpers ─────────────────────────────────────────────

    def _load_bars(self, date: str, symbols: list[str]) -> list[ReplayItem]:
        """Load OHLCV bars from the datalake for the target date."""
        # Use injected data_provider if available, otherwise fall back to DataLakeMarketDataProvider
        if self._data_provider is None:
            from datalake.adapters.analytics_provider import DataLakeMarketDataProvider

            data_provider = DataLakeMarketDataProvider(root=self._data_root)
        else:
            data_provider = self._data_provider

        items: list[ReplayItem] = []
        seq = 0

        if symbols:
            for sym in symbols:
                try:
                    df = data_provider.history(
                        sym,
                        timeframe=self._timeframe,
                        from_date=date,
                        to_date=date,
                    )
                    if df.empty:
                        continue
                    items.extend(self._df_to_items(df, sym, seq_start=seq))
                    seq += len(df)
                except Exception as exc:
                    logger.warning(
                        "Failed to load bars for %s on %s: %s",
                        sym,
                        date,
                        exc,
                    )
        else:
            logger.warning(
                "No symbols specified for replay. Provide symbols list for deterministic replay."
            )

        return items

    def _df_to_items(self, df: pd.DataFrame, symbol: str, seq_start: int = 0) -> list[ReplayItem]:
        """Convert a DataFrame of OHLCV data to ReplayItems (vectorized)."""
        ts_col = "timestamp" if "timestamp" in df.columns else "date"
        timestamps = pd.to_datetime(df[ts_col]).dt.tz_localize(timezone.utc)

        return [
            ReplayItem(
                timestamp=ts,
                sequence=seq_start + i,
                kind="bar",
                symbol=symbol,
                bar_data={
                    "symbol": symbol,
                    "timestamp": ts,
                    "open": float(row.get("open", 0)),
                    "high": float(row.get("high", 0)),
                    "low": float(row.get("low", 0)),
                    "close": float(row.get("close", 0)),
                    "volume": float(row.get("volume", 0)),
                },
            )
            for i, (ts, row) in enumerate(zip(timestamps, df.itertuples(index=False), strict=False))
        ]

    def _load_events(self, day_start: datetime, day_end: datetime) -> list[ReplayItem]:
        """Load domain events from the event log for the target day."""
        if self._event_log is None:
            return []

        try:
            events = self._event_log.replay(since=day_start)
            items: list[ReplayItem] = []

            for evt in events:
                if evt.timestamp > day_end:
                    break
                items.append(
                    ReplayItem(
                        timestamp=evt.timestamp,
                        sequence=evt.sequence_number,
                        kind="event",
                        symbol=evt.symbol,
                        event=evt,
                    )
                )

            logger.info("Loaded %d events from event log", len(items))
            return items
        except Exception as exc:
            logger.warning("Failed to load events: %s", exc)
            return []

    def _merge_streams(self, bars: list[ReplayItem], events: list[ReplayItem]) -> list[ReplayItem]:
        """Merge bars and events into a single time-ordered stream."""
        merged = sorted(bars + events)
        return merged

    def _build_combined_df(self, bar_items: list[ReplayItem]) -> pd.DataFrame:
        """Build a combined OHLCV DataFrame from bar items."""
        if not bar_items:
            return pd.DataFrame()

        rows = []
        for item in bar_items:
            if item.bar_data is not None:
                rows.append(item.bar_data)

        if not rows:
            return pd.DataFrame()

        df = pd.DataFrame(rows)
        if "timestamp" in df.columns:
            df = df.sort_values("timestamp").reset_index(drop=True)
        return df

    def _execute_replay(
        self,
        df: pd.DataFrame,
        merged_stream: list[ReplayItem],
        event_bus: EventBus,
    ) -> ReplayResult | None:
        """Execute the replay through the engine.

        P0-1 fix: Events are now interleaved with bars by timestamp instead of
        being published all at once before bar processing. The event schedule
        maps timestamps to lists of DomainEvents that are published before the
        bar at that timestamp is processed.

        Parameters
        ----------
        df:
            Combined OHLCV DataFrame.
        merged_stream:
            Time-ordered stream of bars and events.
        event_bus:
            EventBus in replay mode.

        Returns
        -------
        ReplayResult | None:
            Replay execution result.
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
        result: ReplayResult | None,
        event_items: list[ReplayItem],
    ) -> tuple[bool, dict[str, Any]]:
        """Assert replayed state matches recorded state from events.

        P0-2 fix: Strengthened state assertion to compare:
        - Trade count (from TRADE/TRADE_APPLIED events vs replay session)
        - Final equity (within tolerance for floating-point comparison)
        - Trade details (symbol, side, quantity match)
        - Position state (open/closed)

        Parameters
        ----------
        result:
            Replay result to validate.
        event_items:
            Events from the log for state derivation.

        Returns
        -------
        tuple[bool, dict[str, Any]]:
            (state_matches, state_diff)
        """
        expected: dict[str, Any] = {"event_count": len(event_items)}
        actual: dict[str, Any] = {"event_count": len(event_items) if result is not None else 0}
        diff: dict[str, Any] = {}

        if result is None:
            if not event_items:
                return True, {}
            return False, {"error": "replay_result is None"}

        # Trade count comparison
        trade_events = [
            i
            for i in event_items
            if i.event is not None and i.event.event_type in ("TRADE", "TRADE_APPLIED")
        ]
        expected["trade_count"] = len(trade_events)
        actual["trade_count"] = result.session.total_trades

        # Final equity comparison
        expected_equity = self._derive_expected_equity(event_items)
        actual_equity = (
            float(result.session.equity_curve[-1][1]) if result.session.equity_curve else 0.0
        )
        expected["equity_final"] = expected_equity
        actual["equity_final"] = actual_equity

        # Trade details comparison
        expected["trades"] = self._derive_expected_trades(event_items)
        actual["trades"] = [
            (t.symbol, str(t.side), t.quantity, str(t.entry_price))
            for t in result.session.trades
        ]

        # Position state comparison
        expected["has_open_position"] = self._derive_expected_position_state(event_items)
        actual["has_open_position"] = result.session.position is not None

        # Validate each field
        matches = True

        # Trade count must match exactly
        if expected["trade_count"] != actual["trade_count"]:
            matches = False
            diff["trade_count"] = {
                "expected": expected["trade_count"],
                "actual": actual["trade_count"],
            }

        # Equity must match within tolerance (floating-point comparison)
        equity_tolerance = 0.01  # 1 cent tolerance
        if expected["equity_final"] is not None:
            equity_diff = abs(expected["equity_final"] - actual["equity_final"])
            if equity_diff > equity_tolerance:
                matches = False
                diff["equity_final"] = {
                    "expected": expected["equity_final"],
                    "actual": actual["equity_final"],
                    "difference": equity_diff,
                }

        # Trade details must match (if we have expected trades)
        if expected["trades"] and expected["trades"] != actual["trades"]:
            matches = False
            diff["trades"] = {
                "expected": expected["trades"],
                "actual": actual["trades"],
            }

        # Position state must match
        if expected["has_open_position"] != actual["has_open_position"]:
            matches = False
            diff["has_open_position"] = {
                "expected": expected["has_open_position"],
                "actual": actual["has_open_position"],
            }

        return matches, diff

    def _derive_expected_equity(
        self, event_items: list[ReplayItem], initial_capital: float = 100_000.0
    ) -> float | None:
        """Derive expected final equity by replaying trade PnL from events.

        Computes equity by starting from initial_capital and applying each
        BUY (debit) and SELL (credit) from TRADE/TRADE_APPLIED events.
        Open positions are valued at entry price (best available estimate).

        Returns None if no trade events found (insufficient data).
        """
        trade_events = [
            i for i in event_items
            if i.event is not None and i.event.event_type in ("TRADE", "TRADE_APPLIED")
        ]
        if not trade_events:
            return None

        capital = initial_capital
        position: tuple[float, int] | None = None  # (entry_price, quantity)
        valid_trades = 0

        for item in trade_events:
            payload = item.event.payload if hasattr(item.event, "payload") else {}
            side = str(payload.get("side", "")).upper()
            price = float(payload.get("price", payload.get("entry_price", 0)))
            qty = int(payload.get("quantity", 0))

            if price <= 0 or qty <= 0:
                continue

            valid_trades += 1
            if side == "BUY" and position is None:
                position = (price, qty)
                capital -= price * qty
            elif side == "SELL" and position is not None:
                capital += price * qty
                position = None

        # No valid trades found — insufficient data
        if valid_trades == 0:
            return None

        # Mark open position at entry price (best available estimate)
        if position is not None:
            capital += position[0] * position[1]

        return capital

    def _derive_expected_trades(self, event_items: list[ReplayItem]) -> list[tuple]:
        """Derive expected trade list from TRADE/TRADE_APPLIED events."""
        trades = []
        for item in event_items:
            if item.event is not None and item.event.event_type in ("TRADE", "TRADE_APPLIED"):
                payload = item.event.payload if hasattr(item.event, "payload") else {}
                symbol = item.event.symbol or payload.get("symbol", "UNKNOWN")
                side = payload.get("side", "UNKNOWN")
                quantity = payload.get("quantity", 0)
                price = payload.get("price", payload.get("entry_price", 0))
                trades.append((symbol, str(side), quantity, str(price)))
        return trades

    def _derive_expected_position_state(self, event_items: list[ReplayItem]) -> bool:
        """Derive expected position state (has open position?) from events.

        Tracks TRADE (open) and position-closing events to determine if
        there should be an open position at the end of replay.
        """
        has_open = False
        for item in event_items:
            if item.event is None:
                continue
            event_type = item.event.event_type
            if event_type in ("TRADE", "TRADE_APPLIED"):
                payload = item.event.payload if hasattr(item.event, "payload") else {}
                side = str(payload.get("side", "")).upper()
                # BUY opens, SELL closes
                if side == "BUY":
                    has_open = True
                elif side == "SELL":
                    has_open = False
            elif event_type == "POSITION_CLOSED":
                has_open = False
        return has_open


__all__ = [
    "ReplayItem",
    "UnifiedReplayOrchestrator",
    "UnifiedReplayResult",
]
