"""MCP tool implementations for read-only datalake analysis.

Every tool here is a thin wrapper over existing datalake code
(:class:`ResearchAPI`, :class:`DataCatalog`, :class:`DataQualityEngine`) or
a guarded read-only DuckDB query -- no tool can write to the datalake or
reach a broker (see the plan's "read-only analysis only" scope decision).
"""

from __future__ import annotations

from contextlib import contextmanager

import duckdb
import pandas as pd

from datalake.core.constants import SUPPORTED_TIMEFRAMES
from datalake.mcp.sql_guard import validate_select
from datalake.quality.engine import DataQualityEngine
from datalake.research.api import ResearchAPI
from datalake.storage.catalog import DataCatalog

logger = logging.getLogger(__name__)

DEFAULT_ROOT = "data/lake"

# Equities and indices share the same hive layout (candles/timeframe={tf}/
# symbol={sym}/data.parquet); options use a different underlying/expiry
# partitioning and are deliberately left out of this unified view -- NIFTY
# options sync is still a separate, not-yet-started effort (see task #12
# in this session's tracker). Matches the exact glob pattern validated
# against the real datalake during this session's manual data audit.
_CANDLES_GLOB = "{root}/*/candles/timeframe=*/symbol=*/data.parquet"


def _records(df: pd.DataFrame) -> list[dict[str, Any]]:
    """Convert a DataFrame to JSON-safe records (datetimes -> ISO strings)."""
    if df.empty:
        return []
    out = df.copy()
    for col in out.columns:
        if pd.api.types.is_datetime64_any_dtype(out[col]):
            out[col] = out[col].astype(str)
    records: list[dict[str, Any]] = out.to_dict(orient="records")
    return records


@contextmanager
def _open_candles_connection(glob: str):
    """In-memory DuckDB with a candles view over *glob* (pooled)."""
    from datalake.core.duckdb_utils import get_memory_pool

    pool = get_memory_pool()
    conn = pool.acquire()
    try:
        conn.execute("SET enable_progress_bar=false")
        create_view_sql = f"CREATE VIEW candles AS SELECT * FROM read_parquet('{glob}')"  # noqa: S608
        conn.execute(create_view_sql)
        yield conn
    finally:
        pool.release(conn)


class DatalakeTools:
    """Bound tool implementations sharing one root + read-only catalog."""

    def __init__(self, root: str = DEFAULT_ROOT) -> None:
        self._root = root
        self._research = ResearchAPI(root=root)
        self._catalog = DataCatalog(root=root, read_only=True)
        # No catalog passed here deliberately: DataQualityEngine.check()
        # writes a row via catalog.record_quality() when given one, which
        # would violate this server's read-only-only scope decision and
        # crash anyway against a read_only=True catalog.
        self._quality = DataQualityEngine(root=root)
        from datalake.research.float_data import FloatDataProvider

        self._float_data = FloatDataProvider.default()

    def _candles_glob(self) -> str:
        return _CANDLES_GLOB.format(root=self._root)

    # -- data retrieval -------------------------------------------------

    def history(
        self,
        symbol: str,
        timeframe: str = "1m",
        years: int = 1,
        from_date: str | None = None,
        to_date: str | None = None,
    ) -> list[dict[str, Any]]:
        """Historical OHLCV candles for a symbol."""
        df = self._research.history(
            symbol, years=years, timeframe=timeframe, from_date=from_date, to_date=to_date
        )
        return _records(df)

    def latest(self, symbol: str, timeframe: str = "1m", n: int = 1) -> list[dict[str, Any]]:
        """Most recent N candles for a symbol."""
        return _records(self._research.latest(symbol, timeframe=timeframe, n=n))

    def list_symbols(self, timeframe: str = "1m") -> list[str]:
        """All symbols with on-disk candle data for a timeframe."""
        return self._research.list_available_symbols(timeframe=timeframe)

    # -- catalog metadata -------------------------------------------------

    def symbol_status(self, symbol: str) -> dict[str, Any] | None:
        """Catalog metadata for a symbol: first/last date, row count. None if unregistered."""
        row = self._catalog.get_symbol(symbol)
        if row is None:
            return None
        return {k: (v.isoformat() if hasattr(v, "isoformat") else v) for k, v in row.items()}

    def catalog_summary(self) -> dict[str, Any]:
        """Datalake-wide summary: symbol count, total rows, quality records."""
        return self._catalog.summary()

    def float_data(self, symbol: str) -> dict[str, Any] | None:
        """Float shares, shares outstanding, market cap, and insider/institutional
        holding percentages for a symbol (sourced from yfinance via
        scripts/sync_float_data.py). None if not yet synced for this symbol.
        """
        return self._float_data.get(symbol)

    # -- quality / gaps -------------------------------------------------

    def quality_check(self, symbol: str, timeframe: str = "1m") -> dict[str, Any]:
        """Gap + completeness report for one symbol.

        Caveats: gap_days uses the active exchange's trading calendar, which
        may currently be missing some real holidays (a fix is in progress
        as a separate task) -- treat gap_days as an upper bound, not exact,
        until that lands. Also, completeness_pct is only computed when
        gap_days > 0 -- a symbol with zero gaps reports completeness_pct=0.0
        (pre-existing bug in DataQualityEngine, should read 100.0); treat
        gap_days=0 as "fully complete" regardless of what completeness_pct
        shows.
        """
        report = self._quality.check(symbol, timeframe=timeframe)
        data = dataclasses.asdict(report)
        data["min_date"] = report.min_date.isoformat() if report.min_date else None
        data["max_date"] = report.max_date.isoformat() if report.max_date else None
        data["summary_text"] = report.summary()
        return data

    def health_check(
        self, timeframe: str = "1m", min_rows: int = 10000, sample_limit: int = 20
    ) -> dict[str, Any]:
        """Corruption scan across every symbol for a timeframe: duplicate
        timestamps, OHLC inconsistency, negative volume, future timestamps,
        thin coverage. Runs directly against the real on-disk Parquet files
        (not the legacy `curated/` layout the older `run_health_check()`
        script targets, which is empty in this datalake).
        """
        if timeframe not in SUPPORTED_TIMEFRAMES:
            raise ValueError(
                f"unsupported timeframe {timeframe!r}; supported: {sorted(SUPPORTED_TIMEFRAMES)}"
            )
        glob = self._candles_glob().replace("timeframe=*", f"timeframe={timeframe}")
        checks = {
            "duplicate_timestamps": """
                SELECT symbol, timestamp, count(*) AS n FROM candles
                GROUP BY symbol, timestamp HAVING count(*) > 1
            """,
            "ohlc_inconsistent": """
                SELECT symbol, timestamp, open, high, low, close FROM candles
                WHERE high < low OR high < open OR high < close OR low > open OR low > close
            """,
            "negative_volume": "SELECT symbol, timestamp, volume FROM candles WHERE volume < 0",
            "future_timestamps": "SELECT symbol, timestamp FROM candles WHERE timestamp > now()",
            "outside_session_hours": """
                SELECT symbol, timestamp FROM candles
                WHERE timestamp::TIME < TIME '09:15:00' OR timestamp::TIME > TIME '15:30:00'
            """,
        }
        results: dict[str, Any] = {}
        # `sql` comes only from the hardcoded `checks` dict above (never
        # caller input); min_rows/sample_limit are int()-cast before
        # interpolation, so neither string can carry injected SQL.
        with _open_candles_connection(glob) as conn:
            for name, sql in checks.items():
                count_sql = f"SELECT count(*) FROM ({sql}) t"  # noqa: S608
                sample_sql = f"{sql} LIMIT {int(sample_limit)}"
                count_row = conn.execute(count_sql).fetchone()
                assert count_row is not None  # COUNT(*) always returns exactly one row
                count = count_row[0]
                sample = conn.execute(sample_sql).df()
                results[name] = {"count": int(count), "sample": _records(sample)}
            thin_sql = (
                f"SELECT symbol, count(*) AS n FROM candles GROUP BY symbol "  # noqa: S608
                f"HAVING count(*) < {int(min_rows)} ORDER BY n LIMIT {int(sample_limit)}"
            )
            thin = conn.execute(thin_sql).df()
            results["thin_coverage"] = {
                "min_rows_threshold": int(min_rows),
                "sample": _records(thin),
            }
        return results

    # -- freeform analysis -------------------------------------------------

    def query(self, sql: str, limit: int = 1000) -> list[dict[str, Any]]:
        """Run a read-only SELECT against the `candles` view (all synced
        equities + indices, every timeframe, unioned by hive partitioning).
        Only SELECT/WITH is allowed -- DDL/DML and filesystem-reaching
        functions (read_parquet, read_csv, ...) are rejected; `candles` is
        the only data source reachable from this connection.
        """
        validate_select(sql)
        limit = max(1, min(int(limit), 10_000))
        with _open_candles_connection(self._candles_glob()) as conn:
            df = conn.execute(sql).df()
        if len(df) > limit:
            df = df.head(limit)
        return _records(df)
