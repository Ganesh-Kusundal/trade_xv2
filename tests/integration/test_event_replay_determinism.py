"""End-to-end smoke test for verify_event_replay.py.

Writes a synthetic event log with a deterministic set of orders and
trades, runs the verifier, and asserts it classifies the state correctly.
"""

from __future__ import annotations

import subprocess
import sys
from decimal import Decimal
from pathlib import Path

from application.oms.context import TradingContext
from application.oms.order_manager import OrderManager
from application.oms.position_manager import PositionManager
from brokers.common.observability.event_metrics import EventMetrics
from domain import (
    Order,
    OrderStatus,
    OrderType,
    ProductType,
    Side,
    Trade,
)
from domain.events.types import EventType  # P1-3: EventType enum
from infrastructure.event_bus import DomainEvent, ProcessedTradeRepository
from infrastructure.event_log import EventLog


def _bootstrap_context(
    events_dir: Path, repo_path: Path | None = None
) -> tuple[TradingContext, ProcessedTradeRepository, EventLog]:
    metrics = EventMetrics()
    from infrastructure.event_bus import DeadLetterQueue

    dlq = DeadLetterQueue()
    from infrastructure.event_bus import EventBus

    log = EventLog(events_dir=events_dir)
    bus = EventBus(metrics=metrics, dead_letter_queue=dlq, event_log=log)
    from infrastructure.event_bus import ProcessedTradeRepository

    # Use a persistent repo when one is requested so that two sessions
    # (live + replay) share idempotency state. This mirrors production
    # where the ledger survives a restart.
    repo = (
        ProcessedTradeRepository(persistence_path=repo_path)
        if repo_path is not None
        else ProcessedTradeRepository()
    )
    om = OrderManager(event_bus=bus, processed_trade_repository=repo, metrics=metrics)
    pm = PositionManager(event_bus=bus)
    ctx = TradingContext(
        event_bus=bus,
        order_manager=om,
        position_manager=pm,
        processed_trade_repository=repo,
        metrics=metrics,
        dead_letter_queue=dlq,
        replay_events=False,
    )
    return ctx, repo, log


def _order_event(o: Order) -> DomainEvent:
    return DomainEvent(
        event_type=EventType.ORDER_UPDATED.value,  # P1-3: Migrated to EventType enum
        timestamp=o.timestamp or DomainEvent.now(EventType.ORDER_UPDATED.value, {}).timestamp,
        payload={"order": o},
        symbol=o.symbol,
        source="synthetic",
    )


def _trade_event(t: Trade) -> DomainEvent:
    return DomainEvent(
        event_type=EventType.TRADE.value,  # P1-3: Migrated to EventType enum
        timestamp=t.timestamp or DomainEvent.now(EventType.TRADE.value, {}).timestamp,
        payload={"trade": t},
        symbol=t.symbol,
        source="synthetic",
    )


def test_synthetic_session_replays_deterministically(tmp_path: Path) -> None:
    events_dir = tmp_path / "events"
    events_dir.mkdir()

    # Session 1 — write a known stream of orders and trades.
    # The ledger is in-memory; we only need it to be persisted if we
    # want to survive a process restart.
    ctx, _, log = _bootstrap_context(events_dir)
    order = Order(
        order_id="O1",
        symbol="RELIANCE",
        exchange="NSE",
        side=Side.BUY,
        order_type=OrderType.MARKET,
        quantity=10,
        price=Decimal("2500"),
        status=OrderStatus.OPEN,
        avg_price=Decimal("0"),
        filled_quantity=0,
        product_type=ProductType.INTRADAY,
    )
    trade1 = Trade(
        trade_id="T1",
        order_id="O1",
        symbol="RELIANCE",
        exchange="NSE",
        side=Side.BUY,
        quantity=5,
        price=Decimal("2500"),
    )
    trade2 = Trade(
        trade_id="T2",
        order_id="O1",
        symbol="RELIANCE",
        exchange="NSE",
        side=Side.BUY,
        quantity=5,
        price=Decimal("2510"),
    )

    ctx.event_bus.publish(_order_event(order))
    ctx.event_bus.publish(_trade_event(trade1))
    ctx.event_bus.publish(_trade_event(trade2))
    log.close()

    # Verify file was written
    files = list(events_dir.glob("*.jsonl"))
    assert files, "Expected event log file"
    content = files[0].read_text()
    # JSONL uses no whitespace separators. The OMS may emit additional
    # ORDER_UPDATED events as a side effect of state changes; just
    # assert there is at least one of each type we explicitly published.
    assert content.count('"event_type":"ORDER_UPDATED"') >= 1
    assert content.count('"event_type":"TRADE"') == 2
    assert content.count('"event_type":"TRADE_APPLIED"') == 2
    assert content.count('"event_type":"POSITION_UPDATED"') >= 1

    # Session 2 — replay the log into a fresh context and assert the state matches.
    # Crucially, this is a recovery scenario: the OMS in session 2 has a
    # fresh in-memory ledger. It will re-apply every event in order
    # (including the TRADE events) and rebuild the same state. This is
    # the deterministic-replay contract.
    from infrastructure.event_bus import (
        DeadLetterQueue,
        EventBus,
        ProcessedTradeRepository,
    )

    metrics2 = EventMetrics()
    dlq2 = DeadLetterQueue()
    log2 = EventLog(events_dir=events_dir)
    bus2 = EventBus(metrics=metrics2, dead_letter_queue=dlq2, event_log=log2)
    repo2 = ProcessedTradeRepository()
    om2 = OrderManager(event_bus=bus2, processed_trade_repository=repo2, metrics=metrics2)
    pm2 = PositionManager(event_bus=bus2)
    ctx2 = TradingContext(
        event_bus=bus2,
        order_manager=om2,
        position_manager=pm2,
        processed_trade_repository=repo2,
        metrics=metrics2,
        dead_letter_queue=dlq2,
        replay_events=False,
    )
    replayed = log2.replay(
        event_types={EventType.ORDER_UPDATED.value, EventType.TRADE.value}
    )  # P1-3: Migrated to EventType enum
    for event in replayed:
        ctx2.event_bus.publish(event)

    # Compare
    o1 = ctx2.order_manager.get_order("O1")
    assert o1 is not None
    assert o1.filled_quantity == 10
    assert o1.status == OrderStatus.FILLED
    # Avg price: (5*2500 + 5*2510) / 10 = 2505
    assert o1.avg_price == Decimal("2505")

    # Position should be +10
    pos = ctx2.position_manager.get_position("RELIANCE", "NSE")
    assert pos is not None
    assert pos.quantity == 10

    # The processed-trade ledger should have both trades recorded
    assert repo2.size() == 2


def test_duplicate_trade_does_not_double_position(tmp_path: Path) -> None:
    """Replay a session where the same trade event is published twice.

    The OMS must record the trade only once; the position must reflect
    a single fill, not two.
    """
    events_dir = tmp_path / "events"
    events_dir.mkdir()
    repo_path = tmp_path / "processed_trades.jsonl"

    # Session 1 — record the order + one trade + the *same* trade again.
    ctx, _, log = _bootstrap_context(events_dir, repo_path=repo_path)
    order = Order(
        order_id="O1",
        symbol="TCS",
        exchange="NSE",
        side=Side.BUY,
        order_type=OrderType.MARKET,
        quantity=10,
        price=Decimal("3500"),
        status=OrderStatus.OPEN,
        product_type=ProductType.INTRADAY,
    )
    trade = Trade(
        trade_id="T1",
        order_id="O1",
        symbol="TCS",
        exchange="NSE",
        side=Side.BUY,
        quantity=10,
        price=Decimal("3500"),
    )
    ctx.event_bus.publish(_order_event(order))
    ctx.event_bus.publish(_trade_event(trade))
    ctx.event_bus.publish(_trade_event(trade))  # duplicate websocket event
    log.close()

    # Session 2 — replay
    from infrastructure.event_bus import (
        DeadLetterQueue,
        EventBus,
        ProcessedTradeRepository,
    )

    metrics2 = EventMetrics()
    dlq2 = DeadLetterQueue()
    log2 = EventLog(events_dir=events_dir)
    bus2 = EventBus(metrics=metrics2, dead_letter_queue=dlq2, event_log=log2)
    repo2 = ProcessedTradeRepository()
    om2 = OrderManager(event_bus=bus2, processed_trade_repository=repo2, metrics=metrics2)
    pm2 = PositionManager(event_bus=bus2)
    ctx2 = TradingContext(
        event_bus=bus2,
        order_manager=om2,
        position_manager=pm2,
        processed_trade_repository=repo2,
        metrics=metrics2,
        dead_letter_queue=dlq2,
        replay_events=False,
    )
    for event in log2.replay(
        event_types={EventType.ORDER_UPDATED.value, EventType.TRADE.value}
    ):  # P1-3: Migrated to EventType enum
        ctx2.event_bus.publish(event)

    o = ctx2.order_manager.get_order("O1")
    assert o is not None
    assert o.filled_quantity == 10  # NOT 20
    pos = ctx2.position_manager.get_position("TCS", "NSE")
    assert pos is not None
    assert pos.quantity == 10  # NOT 20

    # The metrics should reflect: 1 trade processed, 1 trade duplicated.
    assert (
        metrics2.get(EventType.TRADE.value, "trade_processed") == 1
    )  # P1-3: Migrated to EventType enum
    assert (
        metrics2.get(EventType.TRADE.value, "trade_duplicated") == 1
    )  # P1-3: Migrated to EventType enum


def test_verify_event_replay_script_runs(tmp_path: Path) -> None:
    """The CLI verification script must execute without error on a fresh baseline."""
    events_dir = tmp_path / "events"
    events_dir.mkdir()

    # Build a session and persist the log
    ctx, _, log = _bootstrap_context(events_dir)
    order = Order(
        order_id="O1",
        symbol="INFY",
        exchange="NSE",
        side=Side.BUY,
        order_type=OrderType.MARKET,
        quantity=5,
        price=Decimal("1500"),
        status=OrderStatus.OPEN,
        product_type=ProductType.INTRADAY,
    )
    trade = Trade(
        trade_id="T1",
        order_id="O1",
        symbol="INFY",
        exchange="NSE",
        side=Side.BUY,
        quantity=5,
        price=Decimal("1500"),
    )
    ctx.event_bus.publish(_order_event(order))
    ctx.event_bus.publish(_trade_event(trade))
    log.close()

    # Run the verifier with --record-snapshot to create a baseline.
    # parents[0]=integration, parents[1]=tests, parents[2]=project root.
    project_root = Path(__file__).resolve().parents[2]
    result = subprocess.run(
        [
            sys.executable,
            str(project_root / "scripts" / "verify_event_replay.py"),
            "--events",
            str(events_dir),
            "--record-snapshot",
        ],
        capture_output=True,
        text=True,
        cwd=project_root,
    )
    assert result.returncode == 0, f"verifier failed: {result.stderr}\n{result.stdout}"
    assert "Recorded snapshot" in result.stdout

    # Re-running verify with no changes must succeed.
    result = subprocess.run(
        [
            sys.executable,
            str(project_root / "scripts" / "verify_event_replay.py"),
            "--events",
            str(events_dir),
        ],
        capture_output=True,
        text=True,
        cwd=project_root,
    )
    assert result.returncode == 0, f"verifier failed: {result.stderr}\n{result.stdout}"
    # The verifier logs to stderr (or stdout, depending on log config).
    combined = (result.stdout or "") + (result.stderr or "")
    assert "Replay deterministic" in combined or "events matched" in combined
