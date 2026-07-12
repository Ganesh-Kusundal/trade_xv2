"""CQRS query side (ADR-012).

Public surface for the synchronous, read-only :class:`QueryDispatcher`. The
application/SDK/CLI/API layers read state through this package; handlers never
mutate state or publish events.
"""

from __future__ import annotations

from .dispatcher import QueryDispatcher
from .handlers import CandleQueryHandler, PortfolioQueryHandler
from .query import CandleQuery, PortfolioQuery, Query, QueryResult

__all__ = [
    "Query",
    "QueryResult",
    "CandleQuery",
    "PortfolioQuery",
    "QueryDispatcher",
    "CandleQueryHandler",
    "PortfolioQueryHandler",
]
