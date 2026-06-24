"""EventBus factory helpers.

Provides :func:`create_domain_event` for dependency-injection wiring.
"""

from __future__ import annotations

import logging
from typing import Any

from infrastructure.event_bus.event_bus import DomainEvent

logger = logging.getLogger(__name__)


def create_domain_event(**kwargs: Any) -> DomainEvent:
    """Build a domain event with current timestamp (composition-root helper)."""
    return DomainEvent.now(**kwargs)


__all__ = [
    "create_domain_event",
]
