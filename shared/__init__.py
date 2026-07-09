"""Cross-cutting value objects shared across bounded contexts.

Phase 1 scaffold: thin re-exports from domain until deduplication in Phase 4-5.
"""

from shared.types import (
    BrokerCapabilities,
    HistoricalWindowConstraint,
    RateLimitProfile,
    StreamLimitProfile,
)

__all__ = [
    "BrokerCapabilities",
    "HistoricalWindowConstraint",
    "RateLimitProfile",
    "StreamLimitProfile",
]
