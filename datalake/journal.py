"""Trade journal persistence backed by SQLite (WAL mode).

Migrated from DuckDB to SQLite to eliminate the single-writer lock conflict
that occurred when CLI commands ran concurrently. SQLite in WAL mode supports
many concurrent readers and a single writer without blocking.

Public API (``TradeJournal``) is unchanged from the DuckDB version so callers
in ``cli/commands/journal.py`` and tests keep working without modification.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
from datetime import datetime
from pathlib import Path
from typing import Any

DEFAULT_JOURNAL_PATH = Path("market_data/journal.sqlite")

logger = logging.getLogger(__name__)


# Schema. Uses TEXT for everything that DuckDB would have typed precisely
# (TIMESTAMP, MAP) — SQLite is dynamically typed and we get the same semantics
# by parsing on read. ``metadata`` was ``MAP(VARCHAR, VARCHAR)`` in DuckDB; here
# it's stored as a JSON object string.
TRADES_SCHEMA = """
CREATE TABLE IF NOT EXISTS trade_journal (
    trade_id      TEXT PRIMARY KEY,
    symbol        TEXT NOT NULL,
    strategy      TEXT NOT NULL,
    entry_time    TEXT NOT NULL,
    exit_time     TEXT,
    entry_price   REAL NOT NULL,
    exit_price    REAL,
    quantity      INTEGER NOT NULL,
    side          TEXT NOT NULL,
    pnl           REAL,
    pnl_pct       REAL,
    status        TEXT DEFAULT 'OPEN',
    notes         TEXT,
    metadata      TEXT
);
"""

SCANS_SCHEMA = """
CREATE TABLE IF NOT EXISTS scan_results (
    scan_id        TEXT,
    scanner        TEXT NOT NULL,
    symbol         TEXT NOT NULL,
    score          REAL,
    reasons        TEXT,
    universe_size  INTEGER,
    scanned_at     TEXT DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (scan_id, symbol)
);
"""


def _connect(path: Path, read_only: bool) -> sqlite3.Connection:
    """Open a SQLite connection with WAL + sensible pragmas.

    ``uri=True`` lets us request read-only mode via ``mode=ro``. WAL mode is
    only set on the writer side; opening a read-only connection in WAL just
    works (it sees the WAL file if present).
    """
    if read_only:
        uri = f"file:{path}?mode=ro"
        conn = sqlite3.connect(uri, uri=True, timeout=10.0)
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(path), timeout=10.0)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA foreign_keys=ON")

    conn.row_factory = sqlite3.Row
    return conn


def _table_columns(conn: sqlite3.Connection, table: str) -> list[str]:
    return [row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()]


class TradeJournal:
    """Persistent trade journal backed by SQLite (WAL mode).

    Connections are thread-local so concurrent scanners / strategies can safely
    read and write without sharing a single SQLite connection object.
    """

    def __init__(self, catalog_path: str | Path | None = None, read_only: bool = False) -> None:
        if catalog_path is None:
            catalog_path = DEFAULT_JOURNAL_PATH
        self._path = Path(catalog_path)
        self._read_only = read_only
        self._conns: dict[int, sqlite3.Connection] = {}
        self._lock = threading.RLock()
        self._ensure_conn()

    def _ensure_conn(self) -> sqlite3.Connection:
        tid = threading.current_thread().ident
        if tid is None:
            tid = 0
        with self._lock:
            conn = self._conns.get(tid)
            if conn is not None:
                if self._is_healthy(conn):
                    return conn
                else:
                    logger.warning("TradeJournal: stale connection for thread %d, reconnecting", tid)
                    try:
                        conn.close()
                    except Exception:
                        pass
                    del self._conns[tid]
                    conn = None
            if conn is None:
                conn = _connect(self._path, read_only=self._read_only)
                self._conns[tid] = conn
                if not self._read_only:
                    conn.executescript(TRADES_SCHEMA)
                    conn.executescript(SCANS_SCHEMA)
                    conn.commit()
            return conn

    def _is_healthy(self, conn: sqlite3.Connection) -> bool:
        """Validate that a connection is still usable."""
        try:
            conn.execute("SELECT 1")
            return True
        except Exception:
            return False

    def close(self) -> None:
        with self._lock:
            for conn in list(self._conns.values()):
                try:
                    conn.close()
                except Exception:
                    pass
            self._conns.clear()

    # ─── Trades ──────────────────────────────────────────────────────────────

    def record_trade(
        self,
        trade_id: str,
        symbol: str,
        strategy: str,
        entry_time: datetime,
        entry_price: float,
        quantity: int,
        side: str,
        exit_time: datetime | None = None,
        exit_price: float | None = None,
        notes: str | None = None,
        metadata: dict[str, str] | None = None,
    ) -> None:
        """Record a new trade."""
        pnl = None
        pnl_pct = None
        status = "OPEN"

        if exit_price is not None:
            if side == "BUY":
                pnl = (exit_price - entry_price) * quantity
                pnl_pct = ((exit_price - entry_price) / entry_price) * 100
            else:
                pnl = (entry_price - exit_price) * quantity
                pnl_pct = ((entry_price - exit_price) / entry_price) * 100
            status = "CLOSED"

        conn = self._ensure_conn()
        conn.execute(
            """
            INSERT INTO trade_journal
                (trade_id, symbol, strategy, entry_time, exit_time, entry_price,
                 exit_price, quantity, side, pnl, pnl_pct, status, notes, metadata)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                trade_id, symbol.upper(), strategy,
                _iso(entry_time), _iso(exit_time),
                entry_price, exit_price, quantity, side,
                pnl, pnl_pct, status, notes,
                json.dumps(metadata) if metadata else None,
            ],
        )
        conn.commit()

    def close_trade(
        self,
        trade_id: str,
        exit_time: datetime,
        exit_price: float,
        notes: str | None = None,
    ) -> None:
        """Close an open trade."""
        trade = self.get_trade(trade_id)
        if trade is None:
            raise ValueError(f"Trade {trade_id} not found")

        pnl = None
        pnl_pct = None
        if trade["side"] == "BUY":
            pnl = (exit_price - trade["entry_price"]) * trade["quantity"]
            pnl_pct = ((exit_price - trade["entry_price"]) / trade["entry_price"]) * 100
        else:
            pnl = (trade["entry_price"] - exit_price) * trade["quantity"]
            pnl_pct = ((trade["entry_price"] - exit_price) / exit_price) * 100

        conn = self._ensure_conn()
        conn.execute(
            """
            UPDATE trade_journal
            SET exit_time = ?, exit_price = ?, pnl = ?, pnl_pct = ?, status = 'CLOSED',
                notes = COALESCE(?, notes)
            WHERE trade_id = ?
            """,
            [_iso(exit_time), exit_price, pnl, pnl_pct, notes, trade_id],
        )
        conn.commit()

    def get_trade(self, trade_id: str) -> dict | None:
        """Get a single trade by ID."""
        conn = self._ensure_conn()
        row = conn.execute(
            "SELECT * FROM trade_journal WHERE trade_id = ?", [trade_id]
        ).fetchone()
        return _row_to_dict(row) if row else None

    def get_trades(
        self,
        symbol: str | None = None,
        strategy: str | None = None,
        status: str | None = None,
        limit: int = 100,
    ) -> list[dict]:
        """Query trades with optional filters."""
        conn = self._ensure_conn()
        query = "SELECT * FROM trade_journal WHERE 1=1"
        params: list[Any] = []

        if symbol:
            query += " AND symbol = ?"
            params.append(symbol.upper())
        if strategy:
            query += " AND strategy = ?"
            params.append(strategy)
        if status:
            query += " AND status = ?"
            params.append(status.upper())

        query += " ORDER BY entry_time DESC LIMIT ?"
        params.append(limit)

        return [_row_to_dict(r) for r in conn.execute(query, params).fetchall()]

    def get_trade_summary(
        self,
        strategy: str | None = None,
        symbol: str | None = None,
    ) -> dict:
        """Get trade performance summary."""
        conn = self._ensure_conn()
        query = (
            "SELECT COUNT(*) as total_trades, "
            "       COALESCE(SUM(pnl), 0) as total_pnl, "
            "       COALESCE(AVG(pnl), 0) as avg_pnl, "
            "       COALESCE(SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END), 0) as winning_trades "
            "FROM trade_journal WHERE status = 'CLOSED'"
        )
        params: list[Any] = []

        if strategy:
            query += " AND strategy = ?"
            params.append(strategy)
        if symbol:
            query += " AND symbol = ?"
            params.append(symbol.upper())

        row = conn.execute(query, params).fetchone()
        total_trades = row["total_trades"] or 0
        total_pnl = row["total_pnl"] or 0
        avg_pnl = row["avg_pnl"] or 0
        winning_trades = row["winning_trades"] or 0

        win_rate = winning_trades / total_trades if total_trades > 0 else 0

        return {
            "total_trades": total_trades,
            "total_pnl": total_pnl,
            "avg_pnl": avg_pnl,
            "winning_trades": winning_trades,
            "losing_trades": total_trades - winning_trades,
            "win_rate": win_rate,
        }

    # ─── Scans ───────────────────────────────────────────────────────────────

    def save_scan_result(
        self,
        scan_id: str,
        scanner: str,
        symbol: str,
        score: float | None = None,
        reasons: str | None = None,
        universe_size: int | None = None,
    ) -> None:
        """Save a scan result."""
        import uuid
        if not scan_id:
            scan_id = f"scan_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}_{scanner}_{uuid.uuid4().hex[:8]}"
        conn = self._ensure_conn()
        conn.execute(
            """
            INSERT INTO scan_results (scan_id, scanner, symbol, score, reasons, universe_size)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            [scan_id, scanner, symbol.upper(), score, reasons, universe_size],
        )
        conn.commit()

    def get_recent_scans(self, limit: int = 10) -> list[dict]:
        """Get recent scan snapshots."""
        conn = self._ensure_conn()
        rows = conn.execute(
            """
            SELECT scan_id, scanner, MAX(scanned_at) as scanned_at, COUNT(*) as symbols
            FROM scan_results
            GROUP BY scan_id, scanner
            ORDER BY scanned_at DESC
            LIMIT ?
            """,
            [limit],
        ).fetchall()
        return [
            {"scan_id": r["scan_id"], "scanner": r["scanner"], "scanned_at": r["scanned_at"], "symbols": r["symbols"]}
            for r in rows
        ]

    def get_scan_symbols(self, scan_id: str) -> list[dict]:
        """Get symbols from a specific scan."""
        conn = self._ensure_conn()
        rows = conn.execute(
            "SELECT symbol, score, reasons FROM scan_results WHERE scan_id = ? ORDER BY score DESC",
            [scan_id],
        ).fetchall()
        return [{"symbol": r["symbol"], "score": r["score"], "reasons": r["reasons"]} for r in rows]


def _iso(value: datetime | None) -> str | None:
    """Serialize a datetime as ISO 8601 string (matching DuckDB's TIMESTAMP format)."""
    return value.isoformat() if value is not None else None


def _row_to_dict(row: sqlite3.Row) -> dict:
    """Convert a Row to a dict, parsing JSON metadata back to a Python object."""
    d = dict(row)
    if d.get("metadata"):
        try:
            d["metadata"] = json.loads(d["metadata"])
        except (json.JSONDecodeError, TypeError):
            pass
    return d
