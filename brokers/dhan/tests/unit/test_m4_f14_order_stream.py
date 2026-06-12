"""M4 — F14 regression: order-stream operations are no longer silently masked.

Pre-fix: ``DhanMarketDataProvider.subscribe_order_stream`` (and its
siblings) referenced ``self._order_stream_provider`` only when the
attribute *happened* to be present (``if hasattr(...)``).  When the
factory forgot to wire the order-stream provider (which was the
common case — the factory built ``DhanMarketDataProvider(market_data,
options)`` with no third argument), every order-stream call returned
``False`` silently.  Operators never saw the configuration gap.

Post-fix: the adapter's constructor accepts ``order_stream_provider``
explicitly.  When it is ``None``, mutating operations raise
:class:`OrderStreamNotConfigured` and the status method returns
``connected=None`` (a sentinel distinct from ``connected=False``).
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from brokers.dhan.market_data.market_data_adapter import (
    DhanMarketDataProvider,
    OrderStreamNotConfigured,
)

pytestmark = pytest.mark.unit


def _build_provider(order_stream_provider=None) -> DhanMarketDataProvider:
    return DhanMarketDataProvider(
        market_data_client=MagicMock(),
        options_client=MagicMock(),
        order_stream_provider=order_stream_provider,
    )


class TestF14OrderStreamWiring:
    """F14 — order stream must be loud about missing configuration."""

    def test_no_provider_subscribe_raises_loudly(self) -> None:
        provider = _build_provider(order_stream_provider=None)
        with pytest.raises(OrderStreamNotConfigured):
            provider.subscribe_order_stream(["123", "456"])

    def test_no_provider_unsubscribe_raises_loudly(self) -> None:
        provider = _build_provider(order_stream_provider=None)
        with pytest.raises(OrderStreamNotConfigured):
            provider.unsubscribe_order_stream(["123"])

    def test_no_provider_add_listener_raises_loudly(self) -> None:
        provider = _build_provider(order_stream_provider=None)
        with pytest.raises(OrderStreamNotConfigured):
            provider.add_order_listener(lambda evt: None)

    def test_no_provider_status_returns_none_sentinel(self) -> None:
        provider = _build_provider(order_stream_provider=None)
        status = provider.get_order_stream_status()
        # ``connected`` is None (intentionally unwired), not False
        # (intentionally idle).  This is the F14 fix — callers can
        # distinguish the two.
        assert status["connected"] is None
        assert status["subscriptions"] == 0
        assert status["listeners"] == 0

    def test_with_provider_subscribe_delegates(self) -> None:
        stub_stream = MagicMock()
        stub_stream.subscribe_order_stream.return_value = True
        provider = _build_provider(order_stream_provider=stub_stream)
        assert provider.subscribe_order_stream(["789"]) is True
        stub_stream.subscribe_order_stream.assert_called_once_with(["789"])

    def test_with_provider_status_delegates(self) -> None:
        stub_stream = MagicMock()
        stub_stream.get_order_stream_status.return_value = {
            "connected": True,
            "subscriptions": 2,
            "listeners": 1,
        }
        provider = _build_provider(order_stream_provider=stub_stream)
        status = provider.get_order_stream_status()
        assert status == {"connected": True, "subscriptions": 2, "listeners": 1}
