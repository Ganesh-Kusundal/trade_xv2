"""Tests for ProcessedTradeRepository — the trade idempotency ledger."""
from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from brokers.common.core.domain import Side, Trade
from brokers.common.event_bus import (
    ProcessedTradeRepository,
    TradeIdKey,
)


def _make_trade(trade_id: str = "T1", order_id: str = "O1") -> Trade:
    return Trade(
        trade_id=trade_id,
        order_id=order_id,
        symbol="RELIANCE",
        exchange="NSE",
        side=Side.BUY,
        quantity=10,
        price="2500",
    )


def test_first_trade_is_accepted() -> None:
    repo = ProcessedTradeRepository()
    key = TradeIdKey.from_trade(_make_trade())
    assert repo.mark_processed(key) is True
    assert repo.size() == 1
    assert repo.stats()["duplicates_observed"] == 0


def test_duplicate_trade_is_rejected() -> None:
    repo = ProcessedTradeRepository()
    key = TradeIdKey.from_trade(_make_trade())
    repo.mark_processed(key)
    assert repo.mark_processed(key) is False
    assert repo.size() == 1
    assert repo.stats()["duplicates_observed"] == 1


def test_on_duplicate_callback_fires() -> None:
    seen: list[TradeIdKey] = []
    repo = ProcessedTradeRepository(on_duplicate=seen.append)
    key = TradeIdKey.from_trade(_make_trade())
    repo.mark_processed(key)
    repo.mark_processed(key)
    assert len(seen) == 1
    assert seen[0] == key


def test_on_duplicate_callback_failure_does_not_break_processing() -> None:
    def explode(_key: TradeIdKey) -> None:
        raise RuntimeError("metric pipeline down")

    repo = ProcessedTradeRepository(on_duplicate=explode)
    key = TradeIdKey.from_trade(_make_trade())
    repo.mark_processed(key)
    # Second call must not raise even though the callback does.
    assert repo.mark_processed(key) is False


def test_persistence_roundtrip(tmp_path: Path) -> None:
    path = tmp_path / "trades.jsonl"
    repo1 = ProcessedTradeRepository(persistence_path=path)
    repo1.mark_processed(TradeIdKey.from_trade(_make_trade("T1")))
    repo1.mark_processed(TradeIdKey.from_trade(_make_trade("T2")))

    repo2 = ProcessedTradeRepository(persistence_path=path)
    assert repo2.size() == 2
    assert repo2.is_processed(TradeIdKey.from_trade(_make_trade("T1")))
    assert repo2.is_processed(TradeIdKey.from_trade(_make_trade("T2")))
    assert not repo2.is_processed(TradeIdKey.from_trade(_make_trade("T3")))


def test_persistence_appends_one_line_per_trade(tmp_path: Path) -> None:
    path = tmp_path / "trades.jsonl"
    repo = ProcessedTradeRepository(persistence_path=path)
    repo.mark_processed(TradeIdKey.from_trade(_make_trade("T1")))
    repo.mark_processed(TradeIdKey.from_trade(_make_trade("T2")))
    repo.mark_processed(TradeIdKey.from_trade(_make_trade("T1")))  # duplicate

    lines = path.read_text().splitlines()
    # Duplicates must NOT be persisted — only first-seen trades.
    assert len(lines) == 2
    for line in lines:
        record = json.loads(line)
        assert "trade_id" in record
        assert "recorded_at" in record


def test_corrupt_persistence_lines_are_skipped(tmp_path: Path) -> None:
    path = tmp_path / "trades.jsonl"
    path.write_text(
        json.dumps({"trade_id": "T1"}) + "\n"
        + "this is not json\n"
        + json.dumps({"trade_id": "T2"}) + "\n"
    )
    repo = ProcessedTradeRepository(persistence_path=path)
    assert repo.size() == 2


def test_trade_id_required() -> None:
    repo = ProcessedTradeRepository()
    with pytest.raises(ValueError):
        repo.mark_processed(TradeIdKey(trade_id=""))


def test_concurrent_mark_processed_only_accepts_one(
    tmp_path: Path,
) -> None:
    """The same trade fired from 50 threads must end up processed exactly once."""
    path = tmp_path / "trades.jsonl"
    repo = ProcessedTradeRepository(persistence_path=path)
    key = TradeIdKey.from_trade(_make_trade("RACE"))

    def submit(_i: int) -> bool:
        return repo.mark_processed(key)

    with ThreadPoolExecutor(max_workers=20) as pool:
        results = list(pool.map(submit, range(100)))

    assert sum(results) == 1  # exactly one accepted
    assert repo.size() == 1
    assert repo.stats()["duplicates_observed"] == 99


def test_key_from_payload_extracts_trade_id() -> None:
    trade = _make_trade("T99")
    key = TradeIdKey.from_payload({"trade": trade})
    assert key.trade_id == "T99"
    assert key.order_id == "O1"


def test_key_from_payload_falls_back_to_top_level() -> None:
    key = TradeIdKey.from_payload({"trade_id": "T100", "order_id": "O5"})
    assert key.trade_id == "T100"
    assert key.order_id == "O5"


def test_clear_does_not_delete_persistence_file(tmp_path: Path) -> None:
    path = tmp_path / "trades.jsonl"
    repo = ProcessedTradeRepository(persistence_path=path)
    repo.mark_processed(TradeIdKey.from_trade(_make_trade("T1")))
    repo.clear()
    assert repo.size() == 0
    # File still holds the historical record.
    assert path.exists()
    reloaded = ProcessedTradeRepository(persistence_path=path)
    assert reloaded.size() == 1
