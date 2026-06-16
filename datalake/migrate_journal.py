"""One-shot migration: catalog.duckdb trade_journal + scan_results → journal.sqlite.

Run once after deploying the SQLite-backed TradeJournal. Idempotent: re-running
on an already-migrated database is a no-op (unless ``--force`` is given).

Usage:
    python -m datalake.migrate_journal
    python -m datalake.migrate_journal --force   # overwrite target
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

import duckdb

from datalake.journal import DEFAULT_JOURNAL_PATH, _connect

CATALOG_PATH = Path("market_data/catalog.duckdb")


def _table_exists(conn, table: str) -> bool:
    return conn.execute(
        "SELECT COUNT(*) FROM information_schema.tables WHERE table_name = ?",
        [table],
    ).fetchone()[0] > 0


def _serialize_metadata(value) -> str | None:
    """DuckDB MAP(VARCHAR, VARCHAR) → JSON string for SQLite metadata column."""
    if value is None:
        return None
    if isinstance(value, dict):
        return json.dumps(value)
    return str(value)


def migrate(catalog: Path = CATALOG_PATH, target: Path = DEFAULT_JOURNAL_PATH, *, force: bool = False) -> int:
    if not catalog.exists():
        print(f"[skip] catalog not found: {catalog}")
        return 0

    if target.exists() and not force:
        print(f"[skip] target already exists: {target} (use --force to overwrite)")
        return 0

    if target.exists() and force:
        print(f"[force] removing existing {target}")
        # WAL mode → also remove -wal and -shm sidecars
        for suffix in ("", "-wal", "-shm"):
            p = target.with_name(target.name + suffix) if suffix else target
            if p.exists():
                p.unlink()

    duck = duckdb.connect(str(catalog), read_only=True)
    sql = _connect(target, read_only=False)
    try:
        sql.executescript("""
            CREATE TABLE IF NOT EXISTS trade_journal (
                trade_id TEXT PRIMARY KEY,
                symbol TEXT NOT NULL,
                strategy TEXT NOT NULL,
                entry_time TEXT NOT NULL,
                exit_time TEXT,
                entry_price REAL NOT NULL,
                exit_price REAL,
                quantity INTEGER NOT NULL,
                side TEXT NOT NULL,
                pnl REAL,
                pnl_pct REAL,
                status TEXT DEFAULT 'OPEN',
                notes TEXT,
                metadata TEXT
            );
            CREATE TABLE IF NOT EXISTS scan_results (
                scan_id TEXT,
                scanner TEXT NOT NULL,
                symbol TEXT NOT NULL,
                score REAL,
                reasons TEXT,
                universe_size INTEGER,
                scanned_at TEXT DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (scan_id, symbol)
            );
        """)
        sql.commit()

        migrated = 0

        if _table_exists(duck, "trade_journal"):
            trades = duck.execute("SELECT * FROM trade_journal").fetchall()
            cols = [d[0] for d in duck.execute("DESCRIBE trade_journal").fetchall()]
            for row in trades:
                row_dict = dict(zip(cols, row, strict=False))
                # Convert datetime columns to ISO strings (avoids sqlite3 datetime deprecation)
                for col, val in list(row_dict.items()):
                    if isinstance(val, datetime):
                        row_dict[col] = val.isoformat()
                row_dict["metadata"] = _serialize_metadata(row_dict.get("metadata"))
                placeholders = ",".join(["?"] * len(cols))
                sql.execute(
                    f"INSERT OR REPLACE INTO trade_journal ({','.join(cols)}) VALUES ({placeholders})",
                    list(row_dict.values()),
                )
                migrated += 1

        if _table_exists(duck, "scan_results"):
            scans = duck.execute("SELECT * FROM scan_results").fetchall()
            cols = [d[0] for d in duck.execute("DESCRIBE scan_results").fetchall()]
            for row in scans:
                row_dict = dict(zip(cols, row, strict=False))
                for col, val in list(row_dict.items()):
                    if isinstance(val, datetime):
                        row_dict[col] = val.isoformat()
                placeholders = ",".join(["?"] * len(cols))
                sql.execute(
                    f"INSERT OR REPLACE INTO scan_results ({','.join(cols)}) VALUES ({placeholders})",
                    list(row_dict.values()),
                )
                migrated += 1

        sql.commit()
        print(f"[ok] migrated {migrated} rows from {catalog} → {target}")
        return migrated
    finally:
        duck.close()
        sql.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Migrate trade journal from DuckDB to SQLite")
    parser.add_argument("--catalog", type=Path, default=CATALOG_PATH, help="Source DuckDB catalog")
    parser.add_argument("--target", type=Path, default=DEFAULT_JOURNAL_PATH, help="Target SQLite file")
    parser.add_argument("--force", action="store_true", help="Overwrite existing target")
    args = parser.parse_args()

    try:
        migrate(catalog=args.catalog, target=args.target, force=args.force)
    except Exception as exc:
        print(f"[fail] {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
