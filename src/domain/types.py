"""Backward-compat re-export shim — prefer canonical submodule imports.

All definitions live in their owning submodules:

* :mod:`domain.enums` — ``Side``, ``OrderStatus``, ``OrderType``, ``ProductType``, ``Validity``
* :mod:`domain.market_enums` — ``ExchangeSegment``, ``InstrumentType``
* :mod:`domain.capabilities` — ``Capability``, ``ConnectionStatus``
* :mod:`domain.entities.position` — ``PositionState``, ``POSITION_STATE_TRANSITIONS``
* :mod:`domain.entities.order_lifecycle` — ``ORDER_STATUS_TRANSITIONS``
"""

from __future__ import annotations

from domain.capabilities import Capability, ConnectionStatus
from domain.entities.order_lifecycle import ORDER_STATUS_TRANSITIONS
from domain.entities.position import POSITION_STATE_TRANSITIONS, PositionState
from domain.enums import OrderStatus, OrderType, ProductType, Side, Validity
from domain.market_enums import ExchangeSegment, InstrumentType

__all__ = [
    "ORDER_STATUS_TRANSITIONS",
    "POSITION_STATE_TRANSITIONS",
    "Capability",
    "ConnectionStatus",
    "ExchangeSegment",
    "InstrumentType",
    "OrderStatus",
    "OrderType",
    "PositionState",
    "ProductType",
    "Side",
    "Validity",
]
