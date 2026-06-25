"""Tests for trade journal persistence."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from datalake.journal import TradeJournal


@pytest.fixture
def journal(tmp_path: Path) -> TradeJournal:
    """Create a temporary trade journal for testing."""
    db_path = tmp_path / "test_journal.duckdb"
    j = TradeJournal(catalog_path=db_path)
    yield j
    j.close()


class TestTradeJournalRecord:
    def test_record_open_trade(self, journal: TradeJournal) -> None:
        journal.record_trade(
            trade_id="T001",
            symbol="RELIANCE",
            strategy="momentum",
            entry_time=datetime(2026, 1, 1, 10, 0),
            entry_price=2500.0,
            quantity=10,
            side="BUY",
        )
        trade = journal.get_trade("T001")
        assert trade is not None
        assert trade["symbol"] == "RELIANCE"
        assert trade["status"] == "OPEN"
        assert trade["pnl"] is None

    def test_record_closed_trade(self, journal: TradeJournal) -> None:
        journal.record_trade(
            trade_id="T002",
            symbol="INFY",
            strategy="breakout",
            entry_time=datetime(2026, 1, 1, 10, 0),
            entry_price=1500.0,
            quantity=5,
            side="BUY",
            exit_time=datetime(2026, 1, 2, 15, 0),
            exit_price=1600.0,
        )
        trade = journal.get_trade("T002")
        assert trade is not None
        assert trade["status"] == "CLOSED"
        assert trade["pnl"] == 500.0  # (1600 - 1500) * 5
        assert trade["pnl_pct"] == pytest.approx(6.666, rel=0.01)

    def test_record_sell_trade(self, journal: TradeJournal) -> None:
        journal.record_trade(
            trade_id="T003",
            symbol="TCS",
            strategy="momentum",
            entry_time=datetime(2026, 1, 1, 10, 0),
            entry_price=3500.0,
            quantity=3,
            side="SELL",
            exit_time=datetime(2026, 1, 2, 15, 0),
            exit_price=3400.0,
        )
        trade = journal.get_trade("T003")
        assert trade["pnl"] == 300.0  # (3500 - 3400) * 3
        assert trade["pnl_pct"] == pytest.approx(2.857, rel=0.01)

    def test_record_with_notes(self, journal: TradeJournal) -> None:
        journal.record_trade(
            trade_id="T004",
            symbol="HDFCBANK",
            strategy="rsi",
            entry_time=datetime(2026, 1, 1),
            entry_price=1700.0,
            quantity=8,
            side="BUY",
            notes="Strong momentum",
        )
        trade = journal.get_trade("T004")
        assert trade["notes"] == "Strong momentum"


class TestTradeJournalClose:
    def test_close_open_trade(self, journal: TradeJournal) -> None:
        journal.record_trade(
            trade_id="T010",
            symbol="SBIN",
            strategy="momentum",
            entry_time=datetime(2026, 1, 1),
            entry_price=600.0,
            quantity=20,
            side="BUY",
        )
        journal.close_trade("T010", datetime(2026, 1, 5), 650.0)
        trade = journal.get_trade("T010")
        assert trade["status"] == "CLOSED"
        assert trade["pnl"] == 1000.0  # (650 - 600) * 20

    def test_close_nonexistent_trade(self, journal: TradeJournal) -> None:
        with pytest.raises(ValueError, match="not found"):
            journal.close_trade("NONEXISTENT", datetime.now(), 100.0)

    def test_close_with_notes(self, journal: TradeJournal) -> None:
        journal.record_trade(
            trade_id="T011",
            symbol="ITC",
            strategy="scalp",
            entry_time=datetime(2026, 1, 1),
            entry_price=450.0,
            quantity=50,
            side="BUY",
        )
        journal.close_trade("T011", datetime(2026, 1, 3), 470.0, notes="Took profit early")
        trade = journal.get_trade("T011")
        assert trade["notes"] == "Took profit early"


class TestTradeJournalQuery:
    def test_get_trade(self, journal: TradeJournal) -> None:
        journal.record_trade(
            trade_id="T020",
            symbol="WIPRO",
            strategy="momentum",
            entry_time=datetime(2026, 1, 1),
            entry_price=400.0,
            quantity=25,
            side="BUY",
        )
        trade = journal.get_trade("T020")
        assert trade is not None
        assert trade["trade_id"] == "T020"

    def test_get_nonexistent_trade(self, journal: TradeJournal) -> None:
        trade = journal.get_trade("NONEXISTENT")
        assert trade is None

    def test_get_trades_filter_symbol(self, journal: TradeJournal) -> None:
        journal.record_trade("T030", "RELIANCE", "m", datetime.now(), 100, 1, "BUY")
        journal.record_trade("T031", "INFY", "m", datetime.now(), 100, 1, "BUY")
        trades = journal.get_trades(symbol="RELIANCE")
        assert len(trades) == 1
        assert trades[0]["symbol"] == "RELIANCE"

    def test_get_trades_filter_status(self, journal: TradeJournal) -> None:
        journal.record_trade("T040", "RELIANCE", "m", datetime.now(), 100, 1, "BUY")
        journal.record_trade("T041", "INFY", "m", datetime.now(), 100, 1, "BUY")
        journal.close_trade("T040", datetime.now(), 110)
        open_trades = journal.get_trades(status="OPEN")
        closed_trades = journal.get_trades(status="CLOSED")
        assert len(open_trades) == 1
        assert len(closed_trades) == 1

    def test_get_trades_filter_strategy(self, journal: TradeJournal) -> None:
        journal.record_trade("T050", "RELIANCE", "momentum", datetime.now(), 100, 1, "BUY")
        journal.record_trade("T051", "INFY", "breakout", datetime.now(), 100, 1, "BUY")
        trades = journal.get_trades(strategy="momentum")
        assert len(trades) == 1
        assert trades[0]["strategy"] == "momentum"

    def test_get_trades_limit(self, journal: TradeJournal) -> None:
        for i in range(5):
            journal.record_trade(f"T06{i}", "RELIANCE", "m", datetime.now(), 100, 1, "BUY")
        trades = journal.get_trades(limit=3)
        assert len(trades) == 3


class TestTradeJournalSummary:
    def test_summary_empty(self, journal: TradeJournal) -> None:
        summary = journal.get_trade_summary()
        assert summary["total_trades"] == 0
        assert summary["total_pnl"] == 0
        assert summary["win_rate"] == 0

    def test_summary_with_trades(self, journal: TradeJournal) -> None:
        journal.record_trade(
            "S01",
            "RELIANCE",
            "m",
            datetime.now(),
            100,
            1,
            "BUY",
            exit_time=datetime.now(),
            exit_price=110,
        )
        journal.record_trade(
            "S02",
            "INFY",
            "m",
            datetime.now(),
            100,
            1,
            "BUY",
            exit_time=datetime.now(),
            exit_price=90,
        )
        summary = journal.get_trade_summary()
        assert summary["total_trades"] == 2
        assert summary["total_pnl"] == 0  # 10 + (-10)
        assert summary["winning_trades"] == 1
        assert summary["losing_trades"] == 1
        assert summary["win_rate"] == 0.5

    def test_summary_filter_strategy(self, journal: TradeJournal) -> None:
        journal.record_trade(
            "S10",
            "RELIANCE",
            "momentum",
            datetime.now(),
            100,
            1,
            "BUY",
            exit_time=datetime.now(),
            exit_price=120,
        )
        journal.record_trade(
            "S11",
            "INFY",
            "breakout",
            datetime.now(),
            100,
            1,
            "BUY",
            exit_time=datetime.now(),
            exit_price=90,
        )
        summary = journal.get_trade_summary(strategy="momentum")
        assert summary["total_trades"] == 1
        assert summary["total_pnl"] == 20

    def test_summary_filter_symbol(self, journal: TradeJournal) -> None:
        journal.record_trade(
            "S20",
            "RELIANCE",
            "m",
            datetime.now(),
            100,
            1,
            "BUY",
            exit_time=datetime.now(),
            exit_price=110,
        )
        journal.record_trade(
            "S21",
            "INFY",
            "m",
            datetime.now(),
            100,
            1,
            "BUY",
            exit_time=datetime.now(),
            exit_price=90,
        )
        summary = journal.get_trade_summary(symbol="RELIANCE")
        assert summary["total_trades"] == 1
        assert summary["total_pnl"] == 10


class TestTradeJournalThreadSafety:
    def test_concurrent_record_trade(self, journal: TradeJournal) -> None:
        import threading

        errors: list[Exception] = []

        def record(i: int) -> None:
            try:
                journal.record_trade(
                    trade_id=f"TT{i:04d}",
                    symbol="RELIANCE",
                    strategy="momentum",
                    entry_time=datetime(2026, 1, 1, 10, 0),
                    entry_price=2500.0,
                    quantity=1,
                    side="BUY",
                )
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=record, args=(i,)) for i in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors
        trades = journal.get_trades(limit=100)
        assert len(trades) == 20
