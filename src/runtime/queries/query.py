"""Query contracts for the QueryDispatcher (ADR-012).

A Query is a read-only intent. Handlers MUST NOT mutate state or publish
events — they read from existing projections / domain objects (``PositionManager``,
``QueryExecutor`` over DuckDB/Parquet). This keeps the read path fully decoupled
from the event bus and the command path.

Design rules (import-linter "Dispatcher broker isolation"):
- Queries live in ``runtime.queries`` and depend only on ``domain``.
- Query handlers MUST NOT import ``brokers.*`` or publish events.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Query(ABC):
    """Abstract base for all queries routed by :class:`QueryDispatcher`."""

    @property
    @abstractmethod
    def query_type(self) -> str:
        """Stable routing key used by the dispatcher to select a handler."""
        ...


@dataclass(frozen=True)
class PortfolioQuery(Query):
    """Read positions/portfolio for an account."""

    account_id: str = "default"

    @property
    def query_type(self) -> str:
        return "portfolio"


@dataclass(frozen=True)
class CandleQuery(Query):
    """Read historical candle series for a symbol."""

    symbol: str
    timeframe: str = "1m"
    lookback: int = 300

    @property
    def query_type(self) -> str:
        return "candles"


@dataclass(frozen=True)
class QueryResult:
    """Uniform read result returned synchronously by the dispatcher."""

    success: bool
    data: Any | None = None
    error: str | None = None
