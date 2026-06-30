"""MCP tool definitions — functions exposed as tools for LLM consumption."""

from __future__ import annotations

import json
import logging

from datalake.core.serialization import df_to_records

logger = logging.getLogger(__name__)


def register_tools(mcp) -> None:
    """Register all MCP tools with the server."""

    @mcp.tool()
    def datalake_history(
        symbol: str,
        timeframe: str = "1D",
        days: int = 90,
        from_date: str | None = None,
        to_date: str | None = None,
    ) -> dict:
        """Get OHLCV historical data for a symbol."""
        from datalake.gateway import DataLakeGateway

        gw = DataLakeGateway()
        df = gw.history(symbol, timeframe=timeframe, lookback_days=days,
                        from_date=from_date, to_date=to_date)

        if df.empty:
            return {"symbol": symbol, "data": [], "message": "No data found"}

        return {
            "symbol": symbol,
            "timeframe": timeframe,
            "rows": len(df),
            "data": df_to_records(df)[:100],
        }

    @mcp.tool()
    def datalake_universe(
        universe: str = "NIFTY500",
        as_of_date: str | None = None,
    ) -> dict:
        """Get list of symbols in a universe."""
        from datalake.core.schema import load_universe

        symbols = load_universe(universe, as_of_date=as_of_date)
        return {
            "universe": universe,
            "as_of_date": as_of_date,
            "count": len(symbols),
            "symbols": symbols,
        }

    @mcp.tool()
    def datalake_scan(
        rule: str,
        date: str,
        min_rel_volume: float = 0,
    ) -> dict:
        """Execute a scanner rule and return matching stocks."""
        from datalake.scanner.engine import RuleEngine

        engine = RuleEngine()
        params = {"as_of_date": date}

        try:
            df = engine.execute(rule, params=params)
        except FileNotFoundError:
            rule_dict = json.loads(rule)
            df = engine.execute_rule(rule_dict, params=params)

        return {
            "rule": rule,
            "date": date,
            "count": len(df),
            "results": df_to_records(df),
        }

    @mcp.tool()
    def datalake_quality(
        symbol: str,
        timeframe: str = "1m",
    ) -> dict:
        """Check data quality for a symbol."""
        from datalake.quality.engine import DataQualityEngine

        engine = DataQualityEngine()
        report = engine.check(symbol, timeframe=timeframe)

        return {
            "symbol": symbol,
            "status": report.status,
            "total_rows": report.total_rows,
            "date_range": f"{report.min_date} to {report.max_date}",
            "missing_candles": report.missing_candles,
            "duplicate_candles": report.duplicate_candles,
            "gap_days": report.gap_days,
            "completeness_pct": round(report.completeness_pct, 1),
            "issues": report.issues[:10],
        }

    @mcp.tool()
    def datalake_relative_volume(
        date: str,
        cutoff_time: str = "09:45",
        min_rel_volume: float = 5.0,
        lookback_days: int = 14,
    ) -> dict:
        """Get stocks with high relative volume by a cutoff time."""
        from datalake.analytics.relative_volume import high_rel_volume_stocks

        df = high_rel_volume_stocks(
            target_date=date,
            min_rel_volume=min_rel_volume,
            cutoff_time=cutoff_time,
            lookback_days=lookback_days,
        )

        return {
            "date": date,
            "cutoff_time": cutoff_time,
            "min_rel_volume": min_rel_volume,
            "count": len(df),
            "results": df_to_records(df),
        }

    @mcp.tool()
    def datalake_options(
        underlying: str,
        analysis_type: str = "pcr",
    ) -> dict:
        """Get options analytics for an underlying."""
        from datalake.core.duckdb_utils import DEFAULT_CATALOG_PATH, duckdb_connection

        table_map = {"pcr": "m_pcr", "max_pain": "m_max_pain", "iv_surface": "m_iv_surface"}
        table = table_map.get(analysis_type)
        if not table:
            return {"error": f"Unknown analysis type: {analysis_type}. Use: {list(table_map.keys())}"}

        with duckdb_connection(str(DEFAULT_CATALOG_PATH), read_only=True) as conn:
            result = conn.execute(
                f"SELECT * FROM {table} WHERE underlying = ? ORDER BY timestamp DESC LIMIT 1",
                [underlying],
            ).fetchdf()

        if result.empty:
            return {"underlying": underlying, "analysis_type": analysis_type, "message": "No data"}

        return {
            "underlying": underlying,
            "analysis_type": analysis_type,
            "data": df_to_records(result),
        }

    @mcp.tool()
    def datalake_list_rules() -> dict:
        """List all available scanner rules."""
        from datalake.scanner.engine import RuleEngine

        engine = RuleEngine()
        return {"count": 0, "rules": engine.list_rules()}
