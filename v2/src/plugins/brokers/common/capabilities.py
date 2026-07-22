"""Frozen broker capability flags."""

from __future__ import annotations

from dataclasses import dataclass

from domain.enums import AssetClass
from domain.value_objects import Price, Quantity


@dataclass(frozen=True, slots=True)
class BrokerCapabilities:
    supports_market_order: bool = True
    supports_limit_order: bool = True
    supports_stop_order: bool = False
    supports_modify: bool = True
    supports_cancel: bool = True
    supported_asset_classes: frozenset[AssetClass] = frozenset()
    max_order_quantity: Quantity | None = None
    max_order_value: Price | None = None
