"""Brokers events — re-export of domain event types for the broker layer.

The canonical event definitions live in ``domain.events``; this package is a
convenience surface so broker-layer code imports events from one place.
"""

from __future__ import annotations

from domain.events import *  # noqa: F401,F403  (re-export domain event surface)
from domain.events import __all__ as _domain_events_all

try:
    from domain.events.bus import DomainEventBus  # noqa: F401
    _extra = ["DomainEventBus"]
except Exception:  # pragma: no cover
    _extra = []

__all__ = list(_domain_events_all) + _extra