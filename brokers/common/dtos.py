"""Broker-specific DTOs that extend the canonical domain models with transport metadata.

These DTOs live in the broker layer and carry fields that are concerns of the
transport/API boundary — not the domain. Domain-level consumers (``OrderManager``,
``RiskManager``) never see these extra fields.

Usage
-----
Gateways (``DhanBrokerGateway``, ``UpstoxBrokerGateway``) construct a
``BrokerOrderPayload`` from flat parameters and pass it to the broker adapter::

    from brokers.common.dtos import BrokerOrderPayload

    payload = BrokerOrderPayload(
        symbol=symbol,
        exchange=exchange,
        transaction_type=Side.BUY,
        quantity=10,
        exchange_segment=segment,
        transport_only=True,
    )
    order = adapter.place_order(payload)
"""

from __future__ import annotations

from dataclasses import dataclass

from domain.requests import OrderRequest
from domain.types import ExchangeSegment


@dataclass(slots=True, frozen=False)
class BrokerOrderPayload(OrderRequest):
    """Order request with broker-transport metadata.

    Extends the canonical ``OrderRequest`` with fields that are relevant
    only at the broker-API transport layer:

    * ``exchange_segment`` — broker-specific segment enum
    * ``is_amo`` — After Market Order flag (Upstox)
    * ``algo_name`` — algo identifier for UPSTX orders
    * ``market_protection`` — market protection value
    * ``transport_only`` — skip risk checks (OMS has already validated)
    """

    exchange_segment: ExchangeSegment = ExchangeSegment.NSE
    is_amo: bool = False
    algo_name: str | None = None
    market_protection: int = -1
    transport_only: bool = False


__all__ = [
    "BrokerOrderPayload",
]
