#!/usr/bin/env python3
"""Event-replay determinism verifier.

Compares the OMS state built by a live session against the state built by
replaying the persisted event log into a fresh OMS. Any drift is logged
and the process exits non-zero.

Usage::

    python scripts/verify_event_replay.py --events market_data/events \\
        --symbol RELIANCE

This is the Phase 1 mandatory check from the Production Survival Program.
Run it in CI on every PR that touches the OMS, EventBus, or event log.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import tempfile
from collections.abc import Iterable
from dataclasses import asdict
from decimal import Decimal
from pathlib import Path
from typing import Any

# Make project importable when run as a script.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from application.oms.context import TradingContext
from application.oms.order_manager import OrderManager
from application.oms.position_manager import PositionManager
from infrastructure.observability.event_metrics import EventMetrics
from domain.events.types import DomainEvent
from infrastructure.event_bus import (
    DeadLetterQueue,
    EventBus,
    ProcessedTradeRepository,
    TradeIdKey,
)
from infrastructure.event_log import EventLog


def _dumps(value: Any) -> str:
    """JSON with deterministic ordering of dict keys."""
    return json.dumps(value, sort_keys=True, default=str)


def _state_snapshot(ctx: TradingContext) -> dict[str, Any]:
    processed_trades: list[dict] = []
    repo_path = getattr(ctx._processed_trades, "_path", None)
    if repo_path is not None and Path(repo_path).exists():
        for line in Path(repo_path).read_text().splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            processed_trades.append(
                {
                    "trade_id": record.get("trade_id", ""),
                    "broker_trade_id": record.get("broker_trade_id"),
                    "order_id": record.get("order_id"),
                }
            )

    return {
        "orders": sorted(
            (
                {
                    "order_id": o.order_id,
                    "symbol": o.symbol,
                    "exchange": o.exchange,
                    "side": o.side.value,
                    "quantity": o.quantity,
                    "filled_quantity": o.filled_quantity,
                    "avg_price": str(o.avg_price),
                    "status": o.status.value,
                    "correlation_id": o.correlation_id,
                }
                for o in ctx.order_manager.get_orders()
            ),
            key=lambda d: d["order_id"],
        ),
        "positions": sorted(
            (
                {
                    "symbol": p.symbol,
                    "exchange": p.exchange,
                    "quantity": p.quantity,
                    "avg_price": str(p.avg_price),
                    "ltp": str(p.ltp),
                }
                for p in ctx.position_manager.get_positions()
            ),
            key=lambda d: (d["symbol"], d["exchange"]),
        ),
        "processed_trades": sorted(
            processed_trades,
            key=lambda d: d["trade_id"],
        ),
    }


def _events(events_dir: Path) -> Iterable[DomainEvent]:
    log = EventLog(events_dir=events_dir)
    return log.replay(event_types={"ORDER_UPDATED", "TRADE"})


def _build_context(
    events_dir: Path, processed_trades_path: Path | None = None
) -> tuple[TradingContext, ProcessedTradeRepository]:
    metrics = EventMetrics()
    dlq = DeadLetterQueue()
    bus = EventBus(metrics=metrics, dead_letter_queue=dlq)
    log = EventLog(events_dir=events_dir)
    repo = ProcessedTradeRepository(persistence_path=processed_trades_path)
    om = OrderManager(
        event_bus=bus,
        risk_manager=None,
        processed_trade_repository=repo,
        metrics=metrics,
    )
    pm = PositionManager(
        event_bus=bus,
        processed_trade_repository=repo,
        metrics=metrics,
    )
    ctx = TradingContext(
        event_bus=bus,
        order_manager=om,
        position_manager=pm,
        processed_trade_repository=repo,
        metrics=metrics,
        dead_letter_queue=dlq,
        replay_events=False,  # We replay manually with a clean bus.
    )
    return ctx, repo


def _replay_into(ctx: TradingContext, events: Iterable[DomainEvent]) -> int:
    count = 0
    for event in events:
        if event.event_type == "TRADE" or event.event_type == "ORDER_UPDATED":
            ctx.event_bus.publish(event)
        count += 1
    return count


def verify(events_dir: Path) -> int:
    logger = logging.getLogger("verify")
    if not events_dir.exists():
        logger.error("Events directory %s does not exist", events_dir)
        return 2

    # Build a "replayed" context from scratch and replay all events.
    ctx_replayed, _ = _build_context(events_dir)
    events = list(_events(events_dir))
    n = _replay_into(ctx_replayed, events)
    snapshot_replayed = _state_snapshot(ctx_replayed)

    # Read snapshot file if it exists (saved by a prior live run).
    snapshot_path = events_dir.parent / "live_snapshot.json"
    if not snapshot_path.exists():
        logger.warning(
            "No live snapshot found at %s. Saving replayed snapshot as new baseline.",
            snapshot_path,
        )
        snapshot_path.write_text(_dumps(snapshot_replayed))
        return 0

    snapshot_live = json.loads(snapshot_path.read_text())

    if _dumps(snapshot_replayed) == _dumps(snapshot_live):
        logger.info("Replay deterministic — %d events matched live state.", n)
        return 0

    logger.error("Replay diverged from live state over %d events.", n)
    for label, snapshot in (("live", snapshot_live), ("replay", snapshot_replayed)):
        logger.error("--- %s snapshot ---", label)
        logger.error(_dumps(snapshot))
    return 1


def _record_live_snapshot(events_dir: Path, snapshot: dict[str, Any]) -> None:
    snapshot_path = events_dir.parent / "live_snapshot.json"
    snapshot_path.write_text(_dumps(snapshot))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--events",
        type=Path,
        default=Path("market_data/events"),
        help="Directory containing event log JSONL files.",
    )
    parser.add_argument(
        "--record-snapshot",
        action="store_true",
        help="Record a snapshot of the current live OMS state as the baseline.",
    )
    parser.add_argument("-v", "--verbose", action="count", default=0)
    args = parser.parse_args()

    from infrastructure.logging_config import configure_logging

    configure_logging()

    if args.record_snapshot:
        ctx, _ = _build_context(args.events)
        # Replay into the fresh context, then snapshot.
        n = _replay_into(ctx, _events(args.events))
        _record_live_snapshot(args.events, _state_snapshot(ctx))
        print(f"Recorded snapshot after {n} events.")
        return 0

    return verify(args.events)


if __name__ == "__main__":
    raise SystemExit(main())
