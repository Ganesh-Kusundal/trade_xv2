"""SQLite execution ledger for durable intent and submission state."""

from __future__ import annotations

import sqlite3
import threading
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from domain.constants import SQLITE_BUSY_TIMEOUT_MS
from domain.enums import OrderType, ProductType
from domain.execution_contracts import (
    LedgerFillRecord,
    OrderIntent,
    SubmissionOutcome,
    SubmissionState,
)
from domain.ports.execution_ledger import ExecutionLedgerPort
from domain.enums import Side


def _parse_order_type(raw: str) -> OrderType:
    return OrderType(raw) if not isinstance(raw, OrderType) else raw


def _parse_product_type(raw: str) -> ProductType:
    return ProductType(raw) if not isinstance(raw, ProductType) else raw


class SqliteExecutionLedger(ExecutionLedgerPort):
    """Single-writer ledger for pre-submit intent and broker outcomes.

    This is intentionally narrow: it establishes the durable boundary before
    the larger fill/position projector migration. It does not pretend that an
    order snapshot table is a complete economic ledger.
    """

    def __init__(self, path: Path | str | None = None) -> None:
        from domain.ports.data_catalog import DEFAULT_DATA_PATHS

        if path is None:
            path = str(DEFAULT_DATA_PATHS.execution_ledger_path)
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(str(self._path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=FULL")
        self._conn.execute(f"PRAGMA busy_timeout={SQLITE_BUSY_TIMEOUT_MS}")
        self._init_schema()

    def _init_schema(self) -> None:
        with self._lock:
            self._conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS order_intents (
                    intent_id TEXT PRIMARY KEY,
                    order_id TEXT NOT NULL,
                    correlation_id TEXT NOT NULL UNIQUE,
                    symbol TEXT NOT NULL,
                    exchange TEXT NOT NULL,
                    side TEXT NOT NULL,
                    quantity INTEGER NOT NULL,
                    price TEXT NOT NULL,
                    order_type TEXT NOT NULL,
                    product_type TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    schema_version INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS submission_outcomes (
                    intent_id TEXT PRIMARY KEY REFERENCES order_intents(intent_id),
                    state TEXT NOT NULL,
                    broker_order_id TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    observed_at TEXT,
                    schema_version INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS fill_events (
                    fill_id TEXT PRIMARY KEY,
                    order_id TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    exchange TEXT NOT NULL,
                    side TEXT NOT NULL,
                    quantity INTEGER NOT NULL,
                    cumulative_quantity INTEGER NOT NULL,
                    order_quantity INTEGER NOT NULL,
                    price TEXT NOT NULL,
                    event_time TEXT NOT NULL,
                    schema_version INTEGER NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_fill_events_time
                    ON fill_events(event_time, fill_id);
                """
            )
            self._conn.commit()

    def record_intent(self, intent: OrderIntent) -> None:
        with self._lock:
            existing = self._conn.execute(
                "SELECT * FROM order_intents WHERE intent_id = ?",
                (intent.intent_id,),
            ).fetchone()
            if existing is not None:
                if existing["correlation_id"] != intent.correlation_id:
                    raise ValueError(f"intent_id collision: {intent.intent_id}")
                return
            corr_existing = self._conn.execute(
                "SELECT intent_id FROM order_intents WHERE correlation_id = ?",
                (intent.correlation_id,),
            ).fetchone()
            if corr_existing is not None and corr_existing[0] != intent.intent_id:
                raise ValueError(f"correlation_id collision: {intent.correlation_id}")
            self._conn.execute(
                """
                INSERT INTO order_intents (
                    intent_id, order_id, correlation_id, symbol, exchange, side,
                    quantity, price, order_type, product_type, created_at,
                    schema_version
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    intent.intent_id,
                    intent.order_id,
                    intent.correlation_id,
                    intent.symbol,
                    intent.exchange,
                    intent.side.value,
                    intent.quantity,
                    str(intent.price),
                    intent.order_type.value,
                    intent.product_type.value,
                    intent.created_at.isoformat(),
                    intent.schema_version,
                ),
            )
            self._conn.commit()

    def record_outcome(self, outcome: SubmissionOutcome) -> None:
        observed_at = outcome.observed_at.isoformat() if outcome.observed_at else None
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO submission_outcomes (
                    intent_id, state, broker_order_id, reason, observed_at,
                    schema_version
                ) VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(intent_id) DO UPDATE SET
                    state = excluded.state,
                    broker_order_id = excluded.broker_order_id,
                    reason = excluded.reason,
                    observed_at = excluded.observed_at,
                    schema_version = excluded.schema_version
                """,
                (
                    outcome.intent_id,
                    outcome.state.value,
                    outcome.broker_order_id,
                    outcome.reason,
                    observed_at,
                    outcome.schema_version,
                ),
            )
            self._conn.commit()

    def outcome_for(self, intent_id: str) -> SubmissionOutcome | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM submission_outcomes WHERE intent_id = ?",
                (intent_id,),
            ).fetchone()
        if row is None:
            return None
        observed_at = datetime.fromisoformat(row["observed_at"]) if row["observed_at"] else None
        return SubmissionOutcome(
            intent_id=row["intent_id"],
            state=SubmissionState(row["state"]),
            broker_order_id=row["broker_order_id"],
            reason=row["reason"],
            observed_at=observed_at,
            schema_version=row["schema_version"],
        )

    def intent_for_correlation(self, correlation_id: str) -> OrderIntent | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM order_intents WHERE correlation_id = ?",
                (correlation_id,),
            ).fetchone()
        if row is None:
            return None
        return OrderIntent(
            intent_id=row["intent_id"],
            order_id=row["order_id"],
            correlation_id=row["correlation_id"],
            symbol=row["symbol"],
            exchange=row["exchange"],
            side=Side(row["side"]),
            quantity=row["quantity"],
            price=Decimal(row["price"]),
            order_type=_parse_order_type(row["order_type"]),
            product_type=_parse_product_type(row["product_type"]),
            created_at=datetime.fromisoformat(row["created_at"]),
            schema_version=row["schema_version"],
        )

    def order_id_for_correlation(self, correlation_id: str) -> str | None:
        intent = self.intent_for_correlation(correlation_id)
        return intent.order_id if intent is not None else None

    def record_fill(self, fill: LedgerFillRecord) -> None:
        with self._lock:
            existing = self._conn.execute(
                "SELECT fill_id FROM fill_events WHERE fill_id = ?",
                (fill.fill_id,),
            ).fetchone()
            if existing is not None:
                return
            self._conn.execute(
                """
                INSERT INTO fill_events (
                    fill_id, order_id, symbol, exchange, side, quantity,
                    cumulative_quantity, order_quantity, price, event_time,
                    schema_version
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    fill.fill_id,
                    fill.order_id,
                    fill.symbol,
                    fill.exchange,
                    fill.side.value,
                    fill.quantity,
                    fill.cumulative_quantity,
                    fill.order_quantity,
                    str(fill.price),
                    fill.event_time.isoformat(),
                    fill.schema_version,
                ),
            )
            self._conn.commit()

    def list_fills(self) -> list[LedgerFillRecord]:
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT * FROM fill_events
                ORDER BY event_time ASC, fill_id ASC
                """
            ).fetchall()
        return [
            LedgerFillRecord(
                fill_id=row["fill_id"],
                order_id=row["order_id"],
                symbol=row["symbol"],
                exchange=row["exchange"],
                side=Side(row["side"]),
                quantity=row["quantity"],
                cumulative_quantity=row["cumulative_quantity"],
                order_quantity=row["order_quantity"],
                price=Decimal(row["price"]),
                event_time=datetime.fromisoformat(row["event_time"]),
                schema_version=row["schema_version"],
            )
            for row in rows
        ]

    def close(self) -> None:
        with self._lock:
            self._conn.close()
