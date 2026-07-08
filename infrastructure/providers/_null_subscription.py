"""Shared null subscription — used by providers that don't support live feeds."""

from __future__ import annotations


class NullSubscription:
    """No-op subscription for providers that don't support live data.

    Returned by CsvDataProvider, DataFrameDataProvider, and
    CompositeDataProvider when no live provider is available.
    """

    @property
    def is_active(self) -> bool:
        return False

    def unsubscribe(self) -> None:
        pass
