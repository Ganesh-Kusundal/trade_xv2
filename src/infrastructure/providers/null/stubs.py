"""Shared no-op provider stubs."""

from __future__ import annotations

from domain.ports.protocols import SubscriptionHandle


class NullSubscription(SubscriptionHandle):
    """No-op subscription for static/offline data providers."""

    @property
    def is_active(self) -> bool:
        return False

    def unsubscribe(self) -> None:
        pass
