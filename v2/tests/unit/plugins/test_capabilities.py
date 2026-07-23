"""BrokerCapabilities — frozen feature flags for a venue."""

from __future__ import annotations

from decimal import Decimal

import pytest

from domain.enums import AssetClass
from domain.value_objects import Price, Quantity
from plugins.brokers.common.capabilities import BrokerCapabilities


def test_capabilities_frozen() -> None:
    caps = BrokerCapabilities(
        supported_asset_classes=frozenset({AssetClass.EQUITY}),
    )
    with pytest.raises(Exception):
        caps.supports_market_order = False  # type: ignore[misc]


def test_capabilities_defaults() -> None:
    caps = BrokerCapabilities(
        supported_asset_classes=frozenset({AssetClass.EQUITY}),
    )
    assert caps.supports_market_order is True
    assert caps.supports_limit_order is True
    assert caps.supports_stop_order is False
    assert caps.supports_modify is True
    assert caps.supports_cancel is True
    assert caps.max_order_quantity is None
    assert caps.max_order_value is None


def test_capabilities_custom() -> None:
    caps = BrokerCapabilities(
        supports_market_order=False,
        supports_limit_order=True,
        supports_stop_order=True,
        supports_modify=False,
        supports_cancel=False,
        supported_asset_classes=frozenset({AssetClass.DERIVATIVE, AssetClass.COMMODITY}),
        max_order_quantity=Quantity(Decimal("500")),
        max_order_value=Price(Decimal("50000")),
    )
    assert caps.supports_market_order is False
    assert caps.supports_stop_order is True
    assert caps.supports_cancel is False
    assert caps.supported_asset_classes == frozenset({AssetClass.DERIVATIVE, AssetClass.COMMODITY})
    assert caps.max_order_quantity == Quantity(Decimal("500"))
    assert caps.max_order_value == Price(Decimal("50000"))
