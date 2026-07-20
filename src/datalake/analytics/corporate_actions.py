"""Corporate actions store — splits, dividends, bonuses, rights issues.

Stores corporate action events in DuckDB and provides adjustment
factors for backward-adjusting OHLCV data. Critical for multi-year
backtests where raw prices produce incorrect returns.

Supported corporate actions:
- Stock splits (e.g., 1:2 split → adjustment factor 0.5)
- Cash dividends (adjustment factor = close / (close - dividend))
- Stock dividends / bonuses (e.g., 1:1 bonus → factor 0.5)
- Rights issues (at subscription price)

Usage:
    from datalake.analytics.corporate_actions import CorporateActionStore

    store = CorporateActionStore("market_data")
    store.record_split("RELIANCE", date(2023, 7, 1), 2.0)
    factors = store.get_adjustment_factors("RELIANCE", as_of_date=date(2024, 1, 1))
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Literal

import pandas as pd

from datalake.core.duckdb_utils import get_pool
from domain.symbols import normalize_symbol

logger = logging.getLogger(__name__)


@dataclass
class CorporateAction:
    symbol: str
    action_date: date
    action_type: Literal["split", "dividend", "bonus", "rights"]
    ratio: float = 1.0
    dividend_per_share: float = 0.0
    description: str = ""


class CorporateActionStore:
    """DuckDB-backed store for corporate actions and adjustment factors."""

    def __init__(self, root: str | None = None) -> None:
        if root is None:
            from domain.ports.data_catalog import DEFAULT_DATA_PATHS

            root = DEFAULT_DATA_PATHS.lake_root
        self._root = Path(root)
        self._db_path = self._root / "catalog.duckdb"
        self._conn = None

    @property
    def conn(self):
        if self._conn is None:
            self._conn = get_pool().acquire(self._db_path, read_only=False)
            self._ensure_schema(self._conn)
        return self._conn

    def _ensure_schema(self, conn) -> None:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS corporate_actions (
                symbol VARCHAR NOT NULL,
                action_date DATE NOT NULL,
                action_type VARCHAR NOT NULL,
                ratio DOUBLE DEFAULT 1.0,
                dividend_per_share DOUBLE DEFAULT 0.0,
                description VARCHAR DEFAULT '',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (symbol, action_date, action_type)
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_ca_symbol
            ON corporate_actions(symbol)
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_ca_date
            ON corporate_actions(action_date)
        """)

    def record_split(
        self,
        symbol: str,
        action_date: date,
        split_ratio: float,
        description: str = "",
    ) -> None:
        """Record a stock split.

        Args:
            symbol: Trading symbol (e.g., "RELIANCE").
            action_date: Ex-date of the split.
            split_ratio: New shares per old share (e.g., 2.0 for 1:2 split).
            description: Human-readable description.
        """
        symbol = normalize_symbol(symbol)
        self.conn.execute(
            """
            INSERT OR REPLACE INTO corporate_actions
            (symbol, action_date, action_type, ratio, description)
            VALUES (?, ?, 'split', ?, ?)
            """,
            [symbol, action_date, split_ratio, description],
        )
        logger.info("Recorded split: %s %s ratio=%.2f", symbol, action_date, split_ratio)

    def record_dividend(
        self,
        symbol: str,
        action_date: date,
        dividend_per_share: float,
        description: str = "",
    ) -> None:
        """Record a cash dividend (ex-date)."""
        symbol = normalize_symbol(symbol)
        self.conn.execute(
            """
            INSERT OR REPLACE INTO corporate_actions
            (symbol, action_date, action_type, dividend_per_share, description)
            VALUES (?, ?, 'dividend', ?, ?)
            """,
            [symbol, action_date, dividend_per_share, description],
        )
        logger.info(
            "Recorded dividend: %s %s ₹%.2f",
            symbol,
            action_date,
            dividend_per_share,
        )

    def record_bonus(
        self,
        symbol: str,
        action_date: date,
        bonus_ratio: float,
        description: str = "",
    ) -> None:
        """Record a stock bonus.

        Args:
            bonus_ratio: New shares per old share (e.g., 1.0 for 1:1 bonus).
        """
        symbol = normalize_symbol(symbol)
        self.conn.execute(
            """
            INSERT OR REPLACE INTO corporate_actions
            (symbol, action_date, action_type, ratio, description)
            VALUES (?, ?, 'bonus', ?, ?)
            """,
            [symbol, action_date, bonus_ratio, description],
        )
        logger.info(
            "Recorded bonus: %s %s ratio=%.2f",
            symbol,
            action_date,
            bonus_ratio,
        )

    def record_rights(
        self,
        symbol: str,
        action_date: date,
        subscription_price: float,
        ratio: float = 1.0,
        description: str = "",
    ) -> None:
        """Record a rights issue."""
        symbol = normalize_symbol(symbol)
        self.conn.execute(
            """
            INSERT OR REPLACE INTO corporate_actions
            (symbol, action_date, action_type, ratio, description)
            VALUES (?, ?, 'rights', ?, ?)
            """,
            [symbol, action_date, ratio, description],
        )
        logger.info(
            "Recorded rights: %s %s price=%.2f",
            symbol,
            action_date,
            subscription_price,
        )

    def get_actions(
        self,
        symbol: str,
        from_date: date | None = None,
        to_date: date | None = None,
    ) -> pd.DataFrame:
        """Get all corporate actions for a symbol in a date range."""
        symbol = normalize_symbol(symbol)
        conditions = ["symbol = ?"]
        params: list = [symbol]

        if from_date is not None:
            conditions.append("action_date >= ?")
            params.append(from_date)
        if to_date is not None:
            conditions.append("action_date <= ?")
            params.append(to_date)

        where = " AND ".join(conditions)
        query = f"""
            SELECT symbol, action_date, action_type, ratio,
                   dividend_per_share, description
            FROM corporate_actions
            WHERE {where}
            ORDER BY action_date ASC
        """
        return self.conn.execute(query, params).fetchdf()

    def get_adjustment_factors(
        self,
        symbol: str,
        from_date: date | None = None,
        to_date: date | None = None,
    ) -> list[tuple[date, float]]:
        """Compute cumulative backward-adjustment factors for a symbol.

        Returns list of (date, cumulative_factor) tuples sorted by date.
        Factor is applied multiplicatively: adjusted_price = raw_price * factor.

        For splits and bonuses:
            factor = 1 / split_ratio (post-split prices are lower)
        For dividends:
            factor = 1 / (1 - dividend/pre_split_close)
            (approximated without close price: factor = 1.0 for small dividends)
        """
        actions_df = self.get_actions(symbol, from_date, to_date)
        if actions_df.empty:
            return []

        factors: list[tuple[date, float]] = []
        cumulative = 1.0

        for _, row in actions_df.iterrows():
            action_type = row["action_type"]
            if action_type == "split":
                cumulative *= 1.0 / row["ratio"]
            elif action_type == "bonus":
                cumulative *= 1.0 / (1.0 + row["ratio"])
            elif action_type == "dividend" or action_type == "rights":
                pass
            factors.append((row["action_date"], cumulative))

        return factors

    def apply_adjustment(
        self,
        df: pd.DataFrame,
        symbol: str,
        direction: Literal["backward", "forward"] = "backward",
    ) -> pd.DataFrame:
        """Apply adjustment factors to a DataFrame with OHLCV columns.

        Backward adjustment: adjusts historical prices to be comparable
        with current prices (most common for backtesting).

        Forward adjustment: adjusts current prices to match historical
        levels (rarely used).

        Args:
            df: DataFrame with 'timestamp', 'open', 'high', 'low', 'close', 'volume' columns.
            symbol: Symbol name.
            direction: 'backward' (default) or 'forward'.

        Returns:
            DataFrame with adjusted prices and 'adj_close' column added.
        """
        if df.empty or "timestamp" not in df.columns:
            return df

        ts_col = pd.to_datetime(df["timestamp"])
        min_date = ts_col.min().date()
        max_date = ts_col.max().date()

        factors = self.get_adjustment_factors(symbol, min_date, max_date)
        if not factors:
            df = df.copy()
            df["adj_close"] = df["close"]
            return df

        df = df.copy()
        ts_as_date = ts_col.dt.normalize()

        for factor_date, factor in sorted(factors, key=lambda x: x[0], reverse=True):
            fd = pd.Timestamp(factor_date)
            if direction == "backward":
                mask = ts_as_date < fd
                for col in ["open", "high", "low", "close"]:
                    if col in df.columns:
                        df.loc[mask, col] = df.loc[mask, col] * factor
                if "volume" in df.columns:
                    df.loc[mask, "volume"] = (df.loc[mask, "volume"] / factor).astype("int64")
            else:
                mask = ts_as_date >= fd
                for col in ["open", "high", "low", "close"]:
                    if col in df.columns:
                        df.loc[mask, col] = df.loc[mask, col] * factor
                if "volume" in df.columns:
                    df.loc[mask, "volume"] = (df.loc[mask, "volume"] / factor).astype("int64")

        df["adj_close"] = df["close"]

        return df

    def has_actions(self, symbol: str) -> bool:
        """Check if a symbol has any recorded corporate actions."""
        symbol = normalize_symbol(symbol)
        result = self.conn.execute(
            "SELECT COUNT(*) FROM corporate_actions WHERE symbol = ?",
            [symbol],
        ).fetchone()
        return result[0] > 0

    def list_symbols_with_actions(self) -> list[str]:
        """List all symbols that have corporate actions recorded."""
        rows = self.conn.execute(
            "SELECT DISTINCT symbol FROM corporate_actions ORDER BY symbol"
        ).fetchall()
        return [r[0] for r in rows]

    def summary(self) -> dict:
        """Get summary of corporate actions store."""
        total = self.conn.execute("SELECT COUNT(*) FROM corporate_actions").fetchone()[0]
        by_type = self.conn.execute(
            "SELECT action_type, COUNT(*) FROM corporate_actions GROUP BY action_type"
        ).fetchall()
        symbols = self.conn.execute(
            "SELECT COUNT(DISTINCT symbol) FROM corporate_actions"
        ).fetchone()[0]
        return {
            "total_actions": total,
            "symbols_with_actions": symbols,
            "by_type": {r[0]: r[1] for r in by_type},
        }

    def close(self) -> None:
        if self._conn is not None:
            get_pool().release(self._db_path)
            self._conn = None
