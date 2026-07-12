"""Concrete read-only query handlers (ADR-012).

Each handler reads from an existing projection / domain object and returns a
:class:`QueryResult`. Handlers MUST NOT call ``place_order``, publish events,
or mutate any state — they only read.
"""

from __future__ import annotations

from typing import Any

from .query import CandleQuery, PortfolioQuery, QueryResult


class PortfolioQueryHandler:
    """Reads positions from ``PositionManager`` (no mutation)."""

    handled_type = "portfolio"

    def __init__(self, position_manager: Any) -> None:
        self._position_manager = position_manager

    def handle(self, query: PortfolioQuery) -> QueryResult:
        positions = self._position_manager.get_positions()
        return QueryResult(success=True, data=positions)


class CandleQueryHandler:
    """Reads candle series via ``QueryExecutor`` (DuckDB / Parquet)."""

    handled_type = "candles"

    def __init__(self, query_executor: Any) -> None:
        self._query_executor = query_executor

    def handle(self, query: CandleQuery) -> QueryResult:
        series = self._query_executor.get_candles(
            query.symbol,
            timeframe=query.timeframe,
            lookback=query.lookback,
        )
        return QueryResult(success=True, data=series)
