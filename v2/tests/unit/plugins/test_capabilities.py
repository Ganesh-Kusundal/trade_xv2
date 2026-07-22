"""BrokerCapabilities — frozen feature flags for a venue."""

from __future__ import annotations

import pytest

from domain.enums import ExchangeId
from plugins.brokers.common.capabilities import BrokerCapabilities


def test_capabilities_frozen() -> None:
    caps = BrokerCapabilities(
        supports_market_orders=True,
        supports_limit_orders=True,
        supports_stop_orders=False,
        supports_modify=True,
        supports_websocket=True,
        supports_option_chain=True,
        supports_future_chain=False,
        max_orders_per_second=10,
        supported_exchanges=frozenset({ExchangeId.NSE, ExchangeId.BSE}),
    )
    with pytest.raises(Exception):
        caps.supports_market_orders = False  # type: ignore[misc]


def test_capabilities_fields() -> None:
    caps = BrokerCapabilities(
        supports_market_orders=True,
        supports_limit_orders=True,
        supports_stop_orders=True,
        supports_modify=False,
        supports_websocket=False,
        supports_option_chain=False,
        supports_future_chain=True,
        max_orders_per_second=5,
        supported_exchanges=frozenset({ExchangeId.MCX}),
    )
    assert caps.supports_market_orders is True
    assert caps.supports_modify is False
    assert caps.max_orders_per_second == 5
    assert caps.supported_exchanges == frozenset({ExchangeId.MCX})
