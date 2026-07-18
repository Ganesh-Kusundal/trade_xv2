"""Domain services — thin orchestration wrappers over the provider ports.

These are *application-layer* collaborators that sit between the pure
``Instrument`` domain object and the ``DataProvider`` / ``ExecutionProvider``
ports.  They add cross-cutting concerns (caching, staleness windows, simple
metrics) without owning any domain state and without importing any broker
or transport code.

The ``Instrument`` composes these internally (the constructor signature stays
backward compatible) — see ``domain.instruments.instrument``.
"""

from __future__ import annotations

from domain.services.analytics import AnalyticsService
from domain.services.history import HistoryService
from domain.services.orders import OrderService

__all__ = [
    "AnalyticsService",
    "HistoryService",
    "OrderService",
]
