"""Tests for UnifiedReplayOrchestrator — deterministic event+bar replay.

Covers:
- ReplayItem ordering (timestamp, sequence)
- Stream merging (bars + events sorted correctly)
- DataFrame building from bar items
- State assertion logic (match and mismatch)
- No-data returns empty result
- Empty pipeline returns None replay_result
"""

from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd
import pytest

from analytics.replay.orchestrator import (
    ReplayItem,
    UnifiedReplayOrchestrator,
    UnifiedReplayResult,
)
from infrastructure.event_bus.event_bus import DomainEvent


# ---------------------------------------------------------------------------
# ReplayItem ordering
# ---------------------------------------------------------------------------


class TestReplayItemOrdering:
    def test_earlier_timestamp_is_less(self) -> None:
        a = ReplayItem(
            timestamp=datetime(2026, 1, 15, 9, 0, 0, tzinfo=timezone.utc),
            sequence=0,
            kind="bar",
        )
        b = ReplayItem(
            timestamp=datetime(2026, 1, 15, 9, 1, 0, tzinfo=timezone.utc),
            sequence=0,
            kind="event",
        )
        assert a < b

    def test_same_timestamp_uses_sequence(self) -> None:
        """When timestamps are equal, sequence_number breaks the tie."""
        a = ReplayItem(
            timestamp=datetime(2026, 1, 15, 9, 0, 0, tzinfo=timezone.utc),
            sequence=1,
            kind="bar",
        )
        b = ReplayItem(
            timestamp=datetime(2026, 1, 15, 9, 0, 0, tzinfo=timezone.utc),
            sequence=2,
            kind="event",
        )
        assert a < b

    def test_sort_produces_deterministic_order(self) -> None:
        """Sorted ReplayItems should produce a total order."""
        items = [
            ReplayItem(timestamp=datetime(2026, 1, 15, 9, 2, tzinfo=timezone.utc), sequence=0, kind="bar"),
            ReplayItem(timestamp=datetime(2026, 1, 15, 9, 0, tzinfo=timezone.utc), sequence=5, kind="event"),
            ReplayItem(timestamp=datetime(2026, 1, 15, 9, 0, tzinfo=timezone.utc), sequence=3, kind="bar"),
            ReplayItem(timestamp=datetime(2026, 1, 15, 9, 1, tzinfo=timezone.utc), sequence=0, kind="event"),
        ]
        sorted_items = sorted(items)
        assert sorted_items[0].sequence == 3
        assert sorted_items[1].sequence == 5
        assert sorted_items[2].sequence == 0
        assert sorted_items[3].sequence == 0


# ---------------------------------------------------------------------------
# Stream merging
# ---------------------------------------------------------------------------


class TestStreamMerging:
    def test_merge_interleaves_bars_and_events(self) -> None:
        """Bars and events should be merged in timestamp order."""
        orch = UnifiedReplayOrchestrator()
        bars = [
            ReplayItem(
                timestamp=datetime(2026, 1, 15, 9, 0, tzinfo=timezone.utc),
                sequence=0,
                kind="bar",
                symbol="RELIANCE",
            ),
            ReplayItem(
                timestamp=datetime(2026, 1, 15, 9, 2, tzinfo=timezone.utc),
                sequence=1,
                kind="bar",
                symbol="RELIANCE",
            ),
        ]
        events = [
            ReplayItem(
                timestamp=datetime(2026, 1, 15, 9, 1, tzinfo=timezone.utc),
                sequence=0,
                kind="event",
                event=DomainEvent(
                    event_type="TRADE",
                    timestamp=datetime(2026, 1, 15, 9, 1, tzinfo=timezone.utc),
                    payload={"trade_id": "T1"},
                ),
            ),
        ]
        merged = orch._merge_streams(bars, events)
        assert len(merged) == 3
        assert merged[0].kind == "bar"
        assert merged[1].kind == "event"
        assert merged[2].kind == "bar"

    def test_merge_empty_streams(self) -> None:
        """Merging empty lists returns empty list."""
        orch = UnifiedReplayOrchestrator()
        assert orch._merge_streams([], []) == []


# ---------------------------------------------------------------------------
# DataFrame building
# ---------------------------------------------------------------------------


class TestBuildDataFrame:
    def test_builds_ohlcv_from_bar_items(self) -> None:
        """_build_combined_df should produce a DataFrame from bar items."""
        orch = UnifiedReplayOrchestrator()
        items = [
            ReplayItem(
                timestamp=datetime(2026, 1, 15, 9, 0, tzinfo=timezone.utc),
                sequence=0,
                kind="bar",
                symbol="RELIANCE",
                bar_data={
                    "symbol": "RELIANCE",
                    "timestamp": datetime(2026, 1, 15, 9, 0, tzinfo=timezone.utc),
                    "open": 2500.0,
                    "high": 2510.0,
                    "low": 2495.0,
                    "close": 2505.0,
                    "volume": 1000,
                },
            ),
            ReplayItem(
                timestamp=datetime(2026, 1, 15, 9, 1, tzinfo=timezone.utc),
                sequence=1,
                kind="bar",
                symbol="RELIANCE",
                bar_data={
                    "symbol": "RELIANCE",
                    "timestamp": datetime(2026, 1, 15, 9, 1, tzinfo=timezone.utc),
                    "open": 2505.0,
                    "high": 2520.0,
                    "low": 2500.0,
                    "close": 2515.0,
                    "volume": 1500,
                },
            ),
        ]
        df = orch._build_combined_df(items)
        assert len(df) == 2
        assert list(df.columns) == ["symbol", "timestamp", "open", "high", "low", "close", "volume"]
        assert df.iloc[0]["open"] == 2500.0
        assert df.iloc[1]["close"] == 2515.0

    def test_empty_bar_items_returns_empty_df(self) -> None:
        orch = UnifiedReplayOrchestrator()
        assert orch._build_combined_df([]).empty

    def test_event_only_items_returns_empty_df(self) -> None:
        """Items with kind='event' have no bar_data, so df should be empty."""
        orch = UnifiedReplayOrchestrator()
        items = [
            ReplayItem(
                timestamp=datetime(2026, 1, 15, 9, 0, tzinfo=timezone.utc),
                sequence=0,
                kind="event",
                event=DomainEvent(
                    event_type="TRADE",
                    timestamp=datetime(2026, 1, 15, 9, 0, tzinfo=timezone.utc),
                    payload={},
                ),
            ),
        ]
        assert orch._build_combined_df(items).empty


# ---------------------------------------------------------------------------
# State assertion
# ---------------------------------------------------------------------------


class TestStateAssertion:
    def test_matches_when_no_trade_events(self) -> None:
        """When there are no trade events, state assertion passes."""
        orch = UnifiedReplayOrchestrator()
        matches, diff = orch._assert_state(None, [])
        assert matches

    def test_mismatch_when_trade_count_differs(self) -> None:
        """State assertion should detect trade count mismatches."""
        orch = UnifiedReplayOrchestrator()
        # Simulate events with 2 trade events
        trade_events = [
            ReplayItem(
                timestamp=datetime(2026, 1, 15, 9, 0, tzinfo=timezone.utc),
                sequence=i,
                kind="event",
                event=DomainEvent(
                    event_type="TRADE",
                    timestamp=datetime(2026, 1, 15, 9, 0, tzinfo=timezone.utc),
                    payload={"trade_id": f"T{i}"},
                ),
            )
            for i in range(2)
        ]
        # _assert_state expects a result with a .session attribute
        # that has .total_trades, .trades, .equity_curve, .position
        from analytics.replay.models import ReplaySession, SimulatedTrade

        session = ReplaySession()
        session.trades.append(
            SimulatedTrade(
                symbol="RELIANCE",
                side="BUY",
                quantity=100,
                entry_price=2500.0,
                exit_price=2510.0,
                entry_time=datetime(2026, 1, 15, 9, 0, tzinfo=timezone.utc),
                exit_time=datetime(2026, 1, 15, 9, 30, tzinfo=timezone.utc),
                pnl=1000.0,
            )
        )
        session.equity_curve.append(
            (datetime(2026, 1, 15, 9, 0, tzinfo=timezone.utc), 100_000.0)
        )
        # Build a real ReplayResult so _assert_state can access .session
        from analytics.replay.models import ReplayResult, ReplayConfig

        replay_result = ReplayResult(
            session=session,
            config=ReplayConfig(initial_capital=100_000),
        )
        # _assert_state expects ReplayResult | None, not UnifiedReplayResult
        matches, diff = orch._assert_state(replay_result, trade_events)
        # expected trade_count=2, actual trade_count=1 → mismatch
        assert not matches


# ---------------------------------------------------------------------------
# No-data case
# ---------------------------------------------------------------------------


class TestNoDataCase:
    def test_no_data_returns_empty_result(self) -> None:
        """When no bar or event data is found, returns empty result with error."""
        orch = UnifiedReplayOrchestrator(
            events_dir=None,
            data_root="/nonexistent",
        )
        result = orch.run(date="2026-01-15", symbols=["NONEXISTENT"])
        assert not result.state_matches
        assert result.events_replayed == 0
        assert result.bars_replayed == 0
        assert result.state_diff.get("error") == "no data"

    def test_empty_symbols_with_no_event_log(self) -> None:
        """No symbols and no event log should return no data."""
        orch = UnifiedReplayOrchestrator(events_dir=None)
        result = orch.run(date="2026-01-15", symbols=[])
        assert not result.state_matches


# ---------------------------------------------------------------------------
# UnifiedReplayResult
# ---------------------------------------------------------------------------


class TestUnifiedReplayResult:
    def test_summary_includes_core_fields(self) -> None:
        """summary dict should include events_replayed, bars_replayed, state_matches."""
        result = UnifiedReplayResult(
            replay_result=None,
            events_replayed=5,
            bars_replayed=100,
            state_matches=True,
            metadata={"date": "2026-01-15"},
        )
        s = result.summary
        assert s["events_replayed"] == 5
        assert s["bars_replayed"] == 100
        assert s["state_matches"] is True
        assert s["date"] == "2026-01-15"
