"""MCP tool definitions — functions exposed as tools for LLM consumption."""

from __future__ import annotations

import json
import logging
from typing import Any

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
        """Get OHLCV historical data for a symbol.

        Args:
            symbol: Trading symbol (e.g., "RELIANCE", "TCS").
            timeframe: Candle timeframe ("1m", "5m", "15m", "1h", "1D").
            days: Number of days of history (default 90).
            from_date: Start date (YYYY-MM-DD). Overrides days.
            to_date: End date (YYYY-MM-DD).

        Returns:
            Dict with symbol, data (list of OHLCV records), and metadata.
        """
        from datalake.gateway import DataLakeGateway

        gw = DataLakeGateway()
        df = gw.history(symbol, timeframe=timeframe, lookback_days=days,
                        from_date=from_date, to_date=to_date)

        if df.empty:
            return {"symbol": symbol, "data": [], "message": "No data found"}

        records = df.to_dict(orient="records")
        for r in records:
            for k, v in r.items():
                if hasattr(v, "isoformat"):
                    r[k] = v.isoformat()
                elif hasattr(v, "item"):
                    r[k] = v.item()

        return {
            "symbol": symbol,
            "timeframe": timeframe,
            "rows": len(records),
            "data": records[:100],
        }

    @mcp.tool()
    def datalake_universe(
        universe: str = "NIFTY500",
        as_of_date: str | None = None,
    ) -> dict:
        """Get list of symbols in a universe.

        Args:
            universe: Universe name ("NIFTY50", "NIFTY100", "NIFTY200", "NIFTY500").
            as_of_date: Historical date for point-in-time membership (YYYY-MM-DD).

        Returns:
            Dict with universe name, symbol count, and symbol list.
        """
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
        """Execute a scanner rule and return matching stocks.

        Args:
            rule: Rule name (e.g., "volume_spike", "momentum_breakout") or inline JSON rule.
            date: Target date (YYYY-MM-DD).
            min_rel_volume: Minimum relative volume filter (optional).

        Returns:
            Dict with rule name, result count, and matching stocks.
        """
        from datalake.scanner.engine import RuleEngine

        engine = RuleEngine()
        params = {"as_of_date": date}

        try:
            df = engine.execute(rule, params=params)
        except FileNotFoundError:
            rule_dict = json.loads(rule)
            df = engine.execute_rule(rule_dict, params=params)

        records = df.to_dict(orient="records")
        for r in records:
            for k, v in r.items():
                if hasattr(v, "isoformat"):
                    r[k] = v.isoformat()
                elif hasattr(v, "item"):
                    r[k] = v.item()

        return {
            "rule": rule,
            "date": date,
            "count": len(records),
            "results": records,
        }

    @mcp.tool()
    def datalake_quality(
        symbol: str,
        timeframe: str = "1m",
    ) -> dict:
        """Check data quality for a symbol.

        Args:
            symbol: Trading symbol.
            timeframe: Candle timeframe.

        Returns:
            Dict with quality report including completeness, gaps, and issues.
        """
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
        """Get stocks with high relative volume by a cutoff time.

        Args:
            date: Target date (YYYY-MM-DD).
            cutoff_time: Intraday cutoff (e.g., "09:45", "10:00").
            min_rel_volume: Minimum relative volume threshold (default 5.0 = 5x).
            lookback_days: Trading days for average (default 14).

        Returns:
            Dict with date, cutoff, result count, and matching stocks.
        """
        from datalake.analytics.relative_volume import high_rel_volume_stocks

        df = high_rel_volume_stocks(
            target_date=date,
            min_rel_volume=min_rel_volume,
            cutoff_time=cutoff_time,
            lookback_days=lookback_days,
        )

        records = df.to_dict(orient="records")
        for r in records:
            for k, v in r.items():
                if hasattr(v, "isoformat"):
                    r[k] = v.isoformat()
                elif hasattr(v, "item"):
                    r[k] = v.item()

        return {
            "date": date,
            "cutoff_time": cutoff_time,
            "min_rel_volume": min_rel_volume,
            "count": len(records),
            "results": records,
        }

    @mcp.tool()
    def datalake_options(
        underlying: str,
        analysis_type: str = "pcr",
    ) -> dict:
        """Get options analytics for an underlying.

        Args:
            underlying: Underlying symbol (e.g., "NIFTY", "BANKNIFTY").
            analysis_type: Type of analysis ("pcr", "max_pain", "iv_surface").

        Returns:
            Dict with options analytics results.
        """
        import duckdb
        from datalake.core.duckdb_utils import DEFAULT_CATALOG_PATH

        conn = duckdb.connect(str(DEFAULT_CATALOG_PATH), read_only=True)
        try:
            if analysis_type == "pcr":
                sql = """
                    SELECT * FROM m_pcr
                    WHERE underlying = ?
                    ORDER BY timestamp DESC
                    LIMIT 1
                """
            elif analysis_type == "max_pain":
                sql = """
                    SELECT * FROM m_max_pain
                    WHERE underlying = ?
                    ORDER BY timestamp DESC
                    LIMIT 1
                """
            elif analysis_type == "iv_surface":
                sql = """
                    SELECT * FROM m_iv_surface
                    WHERE underlying = ?
                    ORDER BY timestamp DESC
                    LIMIT 1
                """
            else:
                return {"error": f"Unknown analysis type: {analysis_type}"}

            result = conn.execute(sql, [underlying]).fetchdf()
            if result.empty:
                return {"underlying": underlying, "analysis_type": analysis_type, "message": "No data"}

            records = result.to_dict(orient="records")
            for r in records:
                for k, v in r.items():
                    if hasattr(v, "isoformat"):
                        r[k] = v.isoformat()
                    elif hasattr(v, "item"):
                        r[k] = v.item()

            return {
                "underlying": underlying,
                "analysis_type": analysis_type,
                "data": records,
            }
        finally:
            conn.close()

    @mcp.tool()
    def datalake_list_rules() -> dict:
        """List all available scanner rules.

        Returns:
            Dict with list of available rules and their descriptions.
        """
        from datalake.scanner.engine import RuleEngine

        engine = RuleEngine()
        rules = engine.list_rules()
        return {"count": len(rules), "rules": rules}
