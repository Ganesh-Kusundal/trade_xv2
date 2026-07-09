"""Crash recovery tests for ProcessedTradeRepository (canonical layer).

Ensures corrupt JSONL lines do not poison idempotency state on restart.
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
    path = tmp_path / "trades.jsonl"
    repo = ProcessedTradeRepository(persistence_path=path)
    repo.mark_processed(TradeIdKey.from_trade(_make_trade("T1")))
    repo.mark_processed(TradeIdKey.from_trade(_make_trade("T1")))

    lines = path.read_text().splitlines()
    assert len(lines) == 1
    record = json.loads(lines[0])
    assert record["trade_id"] == "T1"


def test_corrupt_line_at_end_is_skipped_on_reload(tmp_path: Path) -> None:
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
    truncated = '{"trade_id":"T2","broker_trade_id":null,"order_i'
    path.write_text(valid + "\n" + truncated)

    repo = ProcessedTradeRepository(persistence_path=path)
    assert repo.size() == 1
    assert repo.is_processed(TradeIdKey.from_trade(_make_trade("T1")))
    assert not repo.is_processed(TradeIdKey.from_trade(_make_trade("T2")))


def test_hot_eviction_still_blocks_redelivery_via_durable_set(tmp_path: Path) -> None:
    """P0-H: after max_age hot eviction, is_processed remains True."""
    path = tmp_path / "trades.jsonl"
    repo = ProcessedTradeRepository(persistence_path=path, max_age_seconds=1)
    key = TradeIdKey.from_trade(_make_trade("T-EVICT"))
    assert repo.mark_processed(key) is True
    # Force timestamps into the past
    import time

    with repo._lock:
        repo._key_timestamps[key] = time.time() - 10_000
    assert repo.cleanup() >= 1
    assert key not in repo._seen  # hot set evicted
    assert repo.is_processed(key) is True  # durable set still holds
    assert repo.mark_processed(key) is False  # redelivery blocked


def test_post_recovery_repo_rejects_duplicate_trades(tmp_path: Path) -> None:
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
    path.write_text(valid + "\n" + '{"trunca')
    repo = ProcessedTradeRepository(persistence_path=path)

    key = TradeIdKey.from_trade(_make_trade("T1"))
    assert repo.is_processed(key)
    assert repo.mark_processed(key) is False

    assert repo.mark_processed(TradeIdKey.from_trade(_make_trade("T-NEW"))) is True
    assert repo.size() == 2
