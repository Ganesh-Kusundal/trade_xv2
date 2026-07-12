"""Synchronous QueryDispatcher (ADR-012).

Routes a :class:`Query` to its handler by ``query_type`` and returns a
:class:`QueryResult`. Query handlers are strictly read-only: they never mutate
state and never publish events. This guarantees the read path cannot
accidentally trigger order flow or side effects.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from .query import Query, QueryResult

logger = logging.getLogger(__name__)

QueryHandler = Callable[[Query], QueryResult]


class QueryDispatcher:
    """Routes queries to read-only handlers and returns results synchronously."""

    def __init__(self) -> None:
        self._handlers: dict[str, QueryHandler] = {}

    def register(self, query_type: str, handler: QueryHandler) -> None:
        self._handlers[query_type] = handler

    def register_handler(self, handler: Any) -> None:
        self.register(handler.handled_type, handler.handle)

    @property
    def registered_types(self) -> list[str]:
        return sorted(self._handlers)

    def dispatch(self, query: Query) -> QueryResult:
        handler = self._handlers.get(query.query_type)
        if handler is None:
            return QueryResult(
                success=False,
                error=f"No handler registered for query '{query.query_type}'",
            )
        return handler(query)
