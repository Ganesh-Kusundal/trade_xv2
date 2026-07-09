"""Tests for domain ports — verify protocol definitions."""

from __future__ import annotations


def test_market_data_port_removed():
    """MarketDataPort has been removed — use brokers.common.api.MarketDataProvider."""
    # This test documents the removal of the orphaned MarketDataPort.
    # All code should now use the broker ISP MarketDataProvider from
    # brokers.common.api instead.
    pass
