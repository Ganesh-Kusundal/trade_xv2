"""Crash recovery for the in-memory ``ProcessedTradeRepository``.

Specifically: a partially-written JSONL line must be skipped on
``load()`` so a process restart does not deadlock on a corrupt
entry. The in-memory implementation (no fsync) simulates a "crash
mid-write" by truncating the last line.

The behavior is the same regardless of whether the persistence file
is on a real filesystem or a tmpfs — the JSONL parser must be
tolerant.
"""

from __future__ import annotations

import json
from pathlib import Path

from domain import Side, Trade
from infrastructure.event_bus import ProcessedTradeRepository, TradeIdKey


def _make_trade(trade_id: str, order_id: str = "O1") -> Trade:
    return Trade(
        trade_id=trade_id,
        order_id=order_id,
        symbol="RELIANCE",
        exchange="NSE",
        side=Side.BUY,
        quantity=10,
        price="2500",
    )


def test_persistence_roundtrip_writes_only_first_seen(tmp_path: Path) -> None:
    """Sanity: a single trade, then the same trade again, must yield
    exactly one persisted line. Duplicates are NOT appended.
    """
    path = tmp_path / "trades.jsonl"
    repo = ProcessedTradeRepository(persistence_path=path)
    repo.mark_processed(TradeIdKey.from_trade(_make_trade("T1")))
    repo.mark_processed(TradeIdKey.from_trade(_make_trade("T1")))  # dup

    lines = path.read_text().splitlines()
    assert len(lines) == 1
    record = json.loads(lines[0])
    assert record["trade_id"] == "T1"


def test_corrupt_line_at_end_is_skipped_on_reload(tmp_path: Path) -> None:
    """Simulate a crash mid-write: a valid line, then a half-written
    line. Re-opening the repo must skip the corrupt line and load
    the valid one.
    """
    path = tmp_path / "trades.jsonl"
    valid = json.dumps(
        {
            "trade_id": "T1",
            "broker_trade_id": None,
            "order_id": "O1",
            "recorded_at": "2026-06-15T10:00:00+00:00",
        },
        separators=(",", ":"),
    )
    # Truncated mid-record (no closing brace, no newline).
    truncated = '{"trade_id":"T2","broker_trade_id":null,"order_i'
    path.write_text(valid + "\n" + truncated)

    repo = ProcessedTradeRepository(persistence_path=path)
    # Only the valid line is in the ledger.
    assert repo.size() == 1
    assert repo.is_processed(TradeIdKey.from_trade(_make_trade("T1")))
    assert not repo.is_processed(TradeIdKey.from_trade(_make_trade("T2")))


def test_corrupt_line_in_middle_is_skipped(tmp_path: Path) -> None:
    """A corrupt line between two valid lines must not poison the
    whole file.
    """
    path = tmp_path / "trades.jsonl"
    line1 = json.dumps(
        {"trade_id": "T1", "broker_trade_id": None, "order_id": "O1"},
        separators=(",", ":"),
    )
    line3 = json.dumps(
        {"trade_id": "T3", "broker_trade_id": None, "order_id": "O3"},
        separators=(",", ":"),
    )
    path.write_text(line1 + "\n" + "GARBAGE_LINE\n" + line3 + "\n")

    repo = ProcessedTradeRepository(persistence_path=path)
    assert repo.size() == 2
    assert repo.is_processed(TradeIdKey.from_trade(_make_trade("T1", order_id="O1")))
    assert not repo.is_processed(TradeIdKey.from_trade(_make_trade("T2")))
    assert repo.is_processed(TradeIdKey.from_trade(_make_trade("T3", order_id="O3")))


def test_blank_lines_and_whitespace_are_tolerated(tmp_path: Path) -> None:
    path = tmp_path / "trades.jsonl"
    path.write_text(
        json.dumps({"trade_id": "T1", "broker_trade_id": None, "order_id": "O1"})
        + "\n"
        + "\n"
        + "   \n"
        + json.dumps({"trade_id": "T2", "broker_trade_id": None, "order_id": "O2"})
        + "\n"
    )
    repo = ProcessedTradeRepository(persistence_path=path)
    assert repo.size() == 2


def test_post_recovery_repo_can_accept_new_trades(tmp_path: Path) -> None:
    """After a crash recovery, the repo must still be able to accept
    new trades (no global lock held by the corrupt line).
    """
    path = tmp_path / "trades.jsonl"
    path.write_text('{"trade_id":"T1"}\n' + '{"trunca')
    repo = ProcessedTradeRepository(persistence_path=path)
    # New trade is accepted.
    assert repo.mark_processed(TradeIdKey.from_trade(_make_trade("T-NEW"))) is True
    assert repo.size() == 2


def test_empty_file_loads_cleanly(tmp_path: Path) -> None:
    path = tmp_path / "trades.jsonl"
    path.write_text("")
    repo = ProcessedTradeRepository(persistence_path=path)
    assert repo.size() == 0
    assert repo.stats()["duplicates_observed"] == 0
