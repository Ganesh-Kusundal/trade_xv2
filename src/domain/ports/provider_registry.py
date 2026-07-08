"""Default data-provider registry (composition-root seam).

The public ``markets`` API is broker-agnostic. A provider is injected here
once, at the composition root (infrastructure), never by importing a broker.
This module imports NOTHING from ``brokers`` — that is the whole point.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from domain.ports.protocols import DataProvider

_provider: "DataProvider | None" = None


def set_default_provider(provider: "DataProvider | None") -> None:
    """Wire the platform-wide data provider (called by the composition root)."""
    global _provider
    _provider = provider


def get_default_provider() -> "DataProvider | None":
    """Return the currently wired provider, or None if not yet composed."""
    return _provider
