"""Persistent SQLite store for API backtest results."""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
from pathlib import Path

from datalake.api.schemas import BacktestMetrics, BacktestResultResponse

logger = logging.getLogger(__name__)

DEFAULT_CACHE_PATH = Path("market_data/backtest_results.sqlite")
MAX_CACHE_ENTRIES = 500


class BacktestCacheStore:
    """SQLite-backed cache for backtest run results."""

    def __init__(self, path: str | Path | None = None) -> None:
        self._path = Path(path) if path else DEFAULT_CACHE_PATH
        self._lock = threading.RLock()
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self._path), timeout=10.0)
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_schema(self) -> None:
        with self._lock:
            conn = self._connect()
            try:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS backtest_results (
                        run_id TEXT PRIMARY KEY,
                        symbol TEXT NOT NULL,
                        timeframe TEXT NOT NULL,
                        payload TEXT NOT NULL,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                conn.commit()
            finally:
                conn.close()

    def save(self, result: BacktestResultResponse) -> None:
        payload = json.dumps(result.model_dump())
        with self._lock:
            conn = self._connect()
            try:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO backtest_results
                    (run_id, symbol, timeframe, payload)
                    VALUES (?, ?, ?, ?)
                    """,
                    [result.run_id, result.symbol, result.timeframe, payload],
                )
                conn.execute(
                    """
                    DELETE FROM backtest_results
                    WHERE run_id NOT IN (
                        SELECT run_id FROM backtest_results
                        ORDER BY created_at DESC
                        LIMIT ?
                    )
                    """,
                    [MAX_CACHE_ENTRIES],
                )
                conn.commit()
            finally:
                conn.close()

    def get(self, run_id: str) -> BacktestResultResponse | None:
        with self._lock:
            conn = self._connect()
            try:
                row = conn.execute(
                    "SELECT payload FROM backtest_results WHERE run_id = ?",
                    [run_id],
                ).fetchone()
            finally:
                conn.close()
        if row is None:
            return None
        data = json.loads(row["payload"])
        return BacktestResultResponse(
            run_id=data["run_id"],
            symbol=data["symbol"],
            timeframe=data["timeframe"],
            metrics=BacktestMetrics(**data["metrics"]),
            trades=data.get("trades"),
        )

    def load_all(self) -> dict[str, BacktestResultResponse]:
        with self._lock:
            conn = self._connect()
            try:
                rows = conn.execute(
                    "SELECT payload FROM backtest_results ORDER BY created_at DESC"
                ).fetchall()
            finally:
                conn.close()
        results: dict[str, BacktestResultResponse] = {}
        for row in rows:
            data = json.loads(row["payload"])
            resp = BacktestResultResponse(
                run_id=data["run_id"],
                symbol=data["symbol"],
                timeframe=data["timeframe"],
                metrics=BacktestMetrics(**data["metrics"]),
                trades=data.get("trades"),
            )
            results[resp.run_id] = resp
        return results
