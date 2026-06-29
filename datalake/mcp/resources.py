"""MCP resource definitions — data exposed as resources for LLM consumption."""

from __future__ import annotations

import json
import logging

logger = logging.getLogger(__name__)


def register_resources(mcp) -> None:
    """Register all MCP resources with the server."""

    @mcp.resource("datalake://schema")
    def get_schema() -> str:
        """Return the canonical OHLCV schema definition."""
        from datalake.core.schema import CANONICAL_COLUMNS, TEMPORAL_COLUMNS

        return json.dumps({
            "name": "OHLCV Schema",
            "columns": CANONICAL_COLUMNS,
            "temporal_columns": TEMPORAL_COLUMNS,
            "timeframes": ["1m", "5m", "15m", "30m", "1h", "1D"],
            "exchanges": ["NSE", "BSE", "NFO"],
        }, indent=2)

    @mcp.resource("datalake://rules")
    def get_rules() -> str:
        """List all available scanner rules."""
        from datalake.scanner.engine import RuleEngine

        engine = RuleEngine()
        rules = engine.list_rules()
        return json.dumps({"rules": rules}, indent=2)

    @mcp.resource("datalake://universe/{name}")
    def get_universe(name: str) -> str:
        """Get universe membership."""
        from datalake.core.schema import load_universe

        symbols = load_universe(name)
        return json.dumps({
            "universe": name,
            "count": len(symbols),
            "symbols": symbols,
        }, indent=2)

    @mcp.resource("datalake://quality/{date}")
    def get_quality(date: str) -> str:
        """Get data quality summary for a date."""
        import duckdb

        from datalake.core.duckdb_utils import DEFAULT_CATALOG_PATH

        conn = duckdb.connect(str(DEFAULT_CATALOG_PATH), read_only=True)
        try:
            result = conn.execute("""
                SELECT
                    symbol,
                    total_rows,
                    missing_candles,
                    duplicate_candles,
                    completeness_pct,
                    status
                FROM data_quality
                WHERE check_date = ?
                ORDER BY symbol
            """, [date]).fetchdf()

            records = result.to_dict(orient="records")
            for r in records:
                for k, v in r.items():
                    if hasattr(v, "item"):
                        r[k] = v.item()

            return json.dumps({
                "date": date,
                "symbols_checked": len(records),
                "issues": [r for r in records if r["status"] != "OK"],
            }, indent=2)
        finally:
            conn.close()
