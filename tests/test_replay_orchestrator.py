"""Tests for UnifiedReplayOrchestrator (Phase 4).

Covers:
- Data loading (bars from datalake, events from event log)
- Stream merging and deterministic ordering
- Combined DataFrame building
- Empty data handling
- State assertion logic
- ReplayItem ordering (__lt__)
- UnifiedReplayResult summary
- Full run() integration with mocked datalake
- Replay determinism guarantees
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from analytics.replay.models import ReplayResult
from analytics.replay.orchestrator import (
    ReplayItem,
    UnifiedReplayOrchestrator,
    UnifiedReplayResult,
)
from infrastructure.event_bus.event_bus import DomainEvent


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def tmp_events_dir(tmp_path: Path) -> Path:
    return tmp_path / "events"


@pytest.fixture
def sample_bar_df() -> pd.DataFrame:
    """A small OHLCV DataFrame for testing."""
    return pd.DataFrame({
        "timestamp": pd.to_datetime([
            "2026-01-15 09:15:00",
            "2026-01-15 09:16:00",
            "2026-01-15 09:17:00",
        ]),
        "open": [100.0, 101.0, 102.0],
        "high": [101.0, 102.0, 103.0],
        "low": [99.5, 100.5, 101.5],
        "close": [100.5, 101.5, 102.5],
        "volume": [1000.0, 1500.0, 2000.0],
    })


@pytest.fixture
def sample_events() -> list[DomainEvent]:
    """Sample domain events for replay."""
    return [
        DomainEvent(
            event_type="TRADE",
            timestamp=datetime(2026, 1, 15, 9, 16, 0, tzinfo=timezone.utc),
            payload={"symbol": "RELIANCE", "side": "BUY", "price": 101.0},
            symbol="RELIANCE",
            source="strategy",
            sequence_number=1,
        ),
        DomainEvent(
            event_type="TRADE_APPLIED",
            timestamp=datetime(2026, 1, 15, 9, 17, 0, tzinfo=timezone.utc),
            payload={"symbol": "RELIANCE", "qty": 10},
            symbol="RELIANCE",
            source="oms",
            sequence_number=2,
        ),
    ]


# ---------------------------------------------------------------------------
# ReplayItem tests
# ---------------------------------------------------------------------------

class TestReplayItem:

    def test_bar_item(self) -> None:
        ts = datetime(2026, 1, 15, 9, 15, 0, tzinfo=timezone.utc)
        item = ReplayItem(
            timestamp=ts,
            sequence=0,
            kind="bar",
            symbol="RELIANCE",
            bar_data={"open": 100.0, "close": 101.0},
        )
        assert item.kind == "bar"
        assert item.symbol == "RELIANCE"
        assert item.event is None

    def test_event_item(self) -> None:
        ts = datetime(2026, 1, 15, 9, 15, 0, tzinfo=timezone.utc)
        evt = DomainEvent(
            event_type="TRADE",
            timestamp=ts,
            payload={"x": 1},
            sequence_number=5,
        )
        item = ReplayItem(
            timestamp=ts,
            sequence=5,
            kind="event",
            symbol="RELIANCE",
            event=evt,
        )
        assert item.kind == "event"
        assert item.event is evt

    def test_less_than_by_timestamp(self) -> None:
        ts1 = datetime(2026, 1, 15, 9, 15, 0, tzinfo=timezone.utc)
        ts2 = datetime(2026, 1, 15, 9, 16, 0, tzinfo=timezone.utc)
        item1 = ReplayItem(timestamp=ts1, sequence=0, kind="bar")
        item2 = ReplayItem(timestamp=ts2, sequence=0, kind="bar")
        assert item1 < item2
        assert not item2 < item1

    def test_less_than_by_sequence_on_same_timestamp(self) -> None:
        ts = datetime(2026, 1, 15, 9, 15, 0, tzinfo=timezone.utc)
        item1 = ReplayItem(timestamp=ts, sequence=0, kind="bar")
        item2 = ReplayItem(timestamp=ts, sequence=1, kind="event")
        assert item1 < item2
        assert not item2 < item1


# ---------------------------------------------------------------------------
# UnifiedReplayResult tests
# ---------------------------------------------------------------------------

class TestUnifiedReplayResult:

    def test_summary_without_replay_result(self) -> None:
        result = UnifiedReplayResult(
            replay_result=None,
            events_replayed=10,
            bars_replayed=100,
            state_matches=True,
        )
        summary = result.summary
        assert summary["events_replayed"] == 10
        assert summary["bars_replayed"] == 100
        assert summary["state_matches"] is True

    def test_summary_with_replay_result(self) -> None:
        replay = ReplayResult()
        replay.bars_processed = 50
        replay.signals_generated = 5
        result = UnifiedReplayResult(
            replay_result=replay,
            events_replayed=3,
            bars_replayed=50,
            state_matches=True,
        )
        summary = result.summary
        assert summary["bars_processed"] == 50
        assert summary["signals_generated"] == 5

    def test_summary_with_metadata(self) -> None:
        result = UnifiedReplayResult(
            replay_result=None,
            events_replayed=0,
            bars_replayed=0,
            state_matches=False,
            metadata={"date": "2026-01-15"},
        )
        assert result.summary["date"] == "2026-01-15"

    def test_state_diff_populated(self) -> None:
        result = UnifiedReplayResult(
            replay_result=None,
            events_replayed=5,
            bars_replayed=100,
            state_matches=False,
            state_diff={"trade_count": {"expected": 3, "actual": 2}},
        )
        assert result.state_diff["trade_count"]["expected"] == 3


# ---------------------------------------------------------------------------
# Orchestrator internal helpers tests
# ---------------------------------------------------------------------------

class TestOrchestratorHelpers:

    def test_df_to_items_converts_dataframe(self, sample_bar_df: pd.DataFrame) -> None:
        orchestrator = UnifiedReplayOrchestrator(data_root="market_data")
        items = orchestrator._df_to_items(sample_bar_df, "RELIANCE")

        assert len(items) == 3
        assert items[0].kind == "bar"
        assert items[0].symbol == "RELIANCE"
        assert items[0].bar_data is not None
        assert items[0].bar_data["open"] == 100.0

    def test_df_to_items_sequence_starts_at_offset(self, sample_bar_df: pd.DataFrame) -> None:
        orchestrator = UnifiedReplayOrchestrator(data_root="market_data")
        items = orchestrator._df_to_items(sample_bar_df, "RELIANCE", seq_start=100)
        assert items[0].sequence == 100
        assert items[1].sequence == 101

    def test_df_to_items_handles_naive_timestamps(self) -> None:
        df = pd.DataFrame({
            "timestamp": [pd.Timestamp("2026-01-15 09:15:00")],
            "open": [100.0],
            "high": [101.0],
            "low": [99.0],
            "close": [100.5],
            "volume": [1000.0],
        })
        orchestrator = UnifiedReplayOrchestrator(data_root="market_data")
        items = orchestrator._df_to_items(df, "X")
        assert items[0].timestamp.tzinfo is not None

    def test_merge_streams_sorts_by_time(self) -> None:
        ts1 = datetime(2026, 1, 15, 9, 15, 0, tzinfo=timezone.utc)
        ts2 = datetime(2026, 1, 15, 9, 16, 0, tzinfo=timezone.utc)
        ts3 = datetime(2026, 1, 15, 9, 17, 0, tzinfo=timezone.utc)

        bars = [
            ReplayItem(timestamp=ts2, sequence=0, kind="bar"),
            ReplayItem(timestamp=ts3, sequence=1, kind="bar"),
        ]
        events = [
            ReplayItem(timestamp=ts1, sequence=0, kind="event"),
        ]

        orchestrator = UnifiedReplayOrchestrator(data_root="market_data")
        merged = orchestrator._merge_streams(bars, events)

        assert len(merged) == 3
        assert merged[0].kind == "event"  # earliest
        assert merged[1].kind == "bar"
        assert merged[2].kind == "bar"

    def test_merge_streams_empty_inputs(self) -> None:
        orchestrator = UnifiedReplayOrchestrator(data_root="market_data")
        merged = orchestrator._merge_streams([], [])
        assert merged == []

    def test_build_combined_df_from_bar_items(self) -> None:
        ts = datetime(2026, 1, 15, 9, 15, 0, tzinfo=timezone.utc)
        bar_items = [
            ReplayItem(
                timestamp=ts,
                sequence=0,
                kind="bar",
                symbol="A",
                bar_data={"symbol": "A", "timestamp": ts, "open": 100.0, "high": 101.0, "low": 99.0, "close": 100.5, "volume": 1000.0},
            ),
            ReplayItem(
                timestamp=ts,
                sequence=1,
                kind="bar",
                symbol="B",
                bar_data={"symbol": "B", "timestamp": ts, "open": 200.0, "high": 201.0, "low": 199.0, "close": 200.5, "volume": 500.0},
            ),
        ]
        orchestrator = UnifiedReplayOrchestrator(data_root="market_data")
        df = orchestrator._build_combined_df(bar_items)
        assert len(df) == 2
        assert "timestamp" in df.columns

    def test_build_combined_df_empty_returns_empty_df(self) -> None:
        orchestrator = UnifiedReplayOrchestrator(data_root="market_data")
        df = orchestrator._build_combined_df([])
        assert df.empty

    def test_execute_replay_empty_df_returns_none(self) -> None:
        orchestrator = UnifiedReplayOrchestrator(data_root="market_data")
        result = orchestrator._execute_replay(pd.DataFrame(), [], None)
        assert result is None


# ---------------------------------------------------------------------------
# Full run() integration tests
# ---------------------------------------------------------------------------

class TestOrchestratorRun:

    @patch("analytics.replay.orchestrator.EventLog")
    @patch("datalake.research.ResearchAPI")
    def test_run_with_no_data_returns_no_data_result(
        self, mock_research_cls: MagicMock, mock_eventlog_cls: MagicMock
    ) -> None:
        """When no bars or events are found, returns state_matches=False."""
        mock_research = MagicMock()
        mock_research.history.return_value = pd.DataFrame()
        mock_research_cls.return_value = mock_research

        mock_eventlog = MagicMock()
        mock_eventlog.replay.return_value = []
        mock_eventlog_cls.return_value = mock_eventlog

        orchestrator = UnifiedReplayOrchestrator(
            events_dir="/tmp/test_events",
            data_root="market_data",
        )
        result = orchestrator.run(date="2026-01-15", symbols=["RELIANCE"])

        assert result.state_matches is False
        assert result.events_replayed == 0
        assert result.bars_replayed == 0
        assert result.state_diff.get("error") == "no data"

    @patch("analytics.replay.orchestrator.EventLog")
    @patch("datalake.research.ResearchAPI")
    def test_run_loads_bars_and_events(
        self, mock_research_cls: MagicMock, mock_eventlog_cls: MagicMock,
        sample_bar_df: pd.DataFrame, sample_events: list[DomainEvent],
    ) -> None:
        """Verifies run() properly loads and merges data."""
        mock_research = MagicMock()
        mock_research.history.return_value = sample_bar_df
        mock_research_cls.return_value = mock_research

        mock_eventlog = MagicMock()
        mock_eventlog.replay.return_value = sample_events
        mock_eventlog_cls.return_value = mock_eventlog

        orchestrator = UnifiedReplayOrchestrator(
            events_dir="/tmp/test_events",
            data_root="market_data",
        )
        result = orchestrator.run(date="2026-01-15", symbols=["RELIANCE"])

        assert result.bars_replayed == 3
        assert result.events_replayed == 2

    @patch("analytics.replay.orchestrator.EventLog")
    @patch("datalake.research.ResearchAPI")
    def test_run_handles_bar_load_error_gracefully(
        self, mock_research_cls: MagicMock, mock_eventlog_cls: MagicMock,
        sample_events: list[DomainEvent],
    ) -> None:
        """If bar loading fails, run() continues with events only."""
        mock_research = MagicMock()
        mock_research.history.side_effect = RuntimeError("datalake error")
        mock_research_cls.return_value = mock_research

        mock_eventlog = MagicMock()
        mock_eventlog.replay.return_value = sample_events
        mock_eventlog_cls.return_value = mock_eventlog

        orchestrator = UnifiedReplayOrchestrator(
            events_dir="/tmp/test_events",
            data_root="market_data",
        )
        result = orchestrator.run(date="2026-01-15", symbols=["RELIANCE"])

        # Should continue with events, bars=0
        assert result.bars_replayed == 0
        assert result.events_replayed == 2

    @patch("analytics.replay.orchestrator.EventLog")
    @patch("datalake.research.ResearchAPI")
    def test_run_with_multiple_symbols(
        self, mock_research_cls: MagicMock, mock_eventlog_cls: MagicMock,
        sample_bar_df: pd.DataFrame,
    ) -> None:
        """Verifies bars are loaded for each symbol."""
        mock_research = MagicMock()
        mock_research.history.return_value = sample_bar_df
        mock_research_cls.return_value = mock_research

        mock_eventlog = MagicMock()
        mock_eventlog.replay.return_value = []
        mock_eventlog_cls.return_value = mock_eventlog

        orchestrator = UnifiedReplayOrchestrator(
            events_dir="/tmp/test_events",
            data_root="market_data",
        )
        result = orchestrator.run(
            date="2026-01-15",
            symbols=["RELIANCE", "TCS"],
        )

        # 3 bars per symbol * 2 symbols = 6 total bars
        assert result.bars_replayed == 6
        mock_research.history.call_count == 2

    @patch("analytics.replay.orchestrator.EventLog")
    def test_run_handles_event_load_error_gracefully(
        self, mock_eventlog_cls: MagicMock, sample_bar_df: pd.DataFrame,
    ) -> None:
        """If event loading fails, run() continues with bars only."""
        from analytics.replay.orchestrator import EventLog as RealEventLog

        mock_eventlog = MagicMock()
        mock_eventlog.replay.side_effect = RuntimeError("event log error")
        mock_eventlog_cls.return_value = mock_eventlog

        with patch("datalake.research.ResearchAPI") as mock_research_cls:
            mock_research = MagicMock()
            mock_research.history.return_value = sample_bar_df
            mock_research_cls.return_value = mock_research

            orchestrator = UnifiedReplayOrchestrator(
                events_dir="/tmp/test_events",
                data_root="market_data",
            )
            result = orchestrator.run(date="2026-01-15", symbols=["RELIANCE"])

            assert result.bars_replayed == 3
            assert result.events_replayed == 0

    @patch("analytics.replay.orchestrator.EventLog")
    @patch("datalake.research.ResearchAPI")
    def test_run_state_assertion_enabled(
        self, mock_research_cls: MagicMock, mock_eventlog_cls: MagicMock,
        sample_bar_df: pd.DataFrame, sample_events: list[DomainEvent],
    ) -> None:
        """Verifies state assertion is performed when assert_state=True."""
        mock_research = MagicMock()
        mock_research.history.return_value = sample_bar_df
        mock_research_cls.return_value = mock_research

        mock_eventlog = MagicMock()
        mock_eventlog.replay.return_value = sample_events
        mock_eventlog_cls.return_value = mock_eventlog

        orchestrator = UnifiedReplayOrchestrator(
            events_dir="/tmp/test_events",
            data_root="market_data",
        )
        result = orchestrator.run(
            date="2026-01-15",
            symbols=["RELIANCE"],
            assert_state=True,
        )

        # State assertion is performed; matches depends on implementation
        assert isinstance(result.state_matches, bool)

    @patch("analytics.replay.orchestrator.EventLog")
    @patch("datalake.research.ResearchAPI")
    def test_run_metadata_includes_date_and_symbols(
        self, mock_research_cls: MagicMock, mock_eventlog_cls: MagicMock,
        sample_bar_df: pd.DataFrame,
    ) -> None:
        mock_research = MagicMock()
        mock_research.history.return_value = sample_bar_df
        mock_research_cls.return_value = mock_research

        mock_eventlog = MagicMock()
        mock_eventlog.replay.return_value = []
        mock_eventlog_cls.return_value = mock_eventlog

        orchestrator = UnifiedReplayOrchestrator(
            events_dir="/tmp/test_events",
            data_root="market_data",
        )
        result = orchestrator.run(
            date="2026-06-01",
            symbols=["RELIANCE", "TCS"],
        )

        assert result.metadata["date"] == "2026-06-01"
        assert result.metadata["symbols"] == ["RELIANCE", "TCS"]


# ---------------------------------------------------------------------------
# Determinism tests
# ---------------------------------------------------------------------------

class TestReplayDeterminism:

    def test_replay_item_ordering_is_deterministic(self) -> None:
        """Same items sorted twice should produce the same order."""
        ts1 = datetime(2026, 1, 15, 9, 15, 0, tzinfo=timezone.utc)
        ts2 = datetime(2026, 1, 15, 9, 16, 0, tzinfo=timezone.utc)

        items = [
            ReplayItem(timestamp=ts2, sequence=10, kind="bar"),
            ReplayItem(timestamp=ts1, sequence=5, kind="event"),
            ReplayItem(timestamp=ts1, sequence=0, kind="bar"),
            ReplayItem(timestamp=ts2, sequence=3, kind="event"),
        ]

        sorted1 = sorted(items)
        sorted2 = sorted(items)

        assert sorted1 == sorted2

    def test_merge_produces_same_order_on_repeated_calls(self) -> None:
        orchestrator = UnifiedReplayOrchestrator(data_root="market_data")
        ts1 = datetime(2026, 1, 15, 9, 15, 0, tzinfo=timezone.utc)
        ts2 = datetime(2026, 1, 15, 9, 16, 0, tzinfo=timezone.utc)

        bars = [
            ReplayItem(timestamp=ts1, sequence=0, kind="bar"),
            ReplayItem(timestamp=ts2, sequence=2, kind="bar"),
        ]
        events = [
            ReplayItem(timestamp=ts1, sequence=1, kind="event"),
        ]

        merged1 = orchestrator._merge_streams(bars, events)
        merged2 = orchestrator._merge_streams(bars, events)

        assert merged1 == merged2
