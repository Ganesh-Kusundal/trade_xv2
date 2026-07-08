"""BrokerTransport — the unified broker port defined by the domain.

A broker plugin implements ``BrokerTransport`` to expose its market-data,
execution, and capability surface as **domain objects** (``InstrumentId`` in,
domain value objects out). This replaces the broker-centric gateway facade as
the public broker boundary: consumers and application workflows depend on this
port, never on a concrete ``BrokerGateway``.

    transport = DhanTransport(gateway)
    quote = transport.market_data.get_quote(instrument_id)   # domain QuoteSnapshot
    result = transport.execution.place_order(order_request)  # domain OrderResult
    if transport.supports(Capability.OPTION_GREEKS): ...

Capability discovery (``supports()``) is the domain-correct replacement for
``if broker == "dhan"`` conditionals.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from domain.capabilities import Capability
from domain.ports.protocols import DataProvider, ExecutionProvider


class BrokerTransport(ABC):
    """Unified broker surface, expressed entirely in domain terms."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Stable broker identifier (e.g. ``"dhan"``)."""

    @property
    @abstractmethod
    def market_data(self) -> DataProvider:
        """Market-data transport (quotes, depth, history, option chains, streaming)."""

    @property
    @abstractmethod
    def execution(self) -> ExecutionProvider:
        """Order/execution transport (place/cancel/modify, positions, holdings, funds)."""

    @abstractmethod
    def capabilities(self) -> list[Capability]:
        """Domain capabilities this broker provides (for dynamic discovery)."""

    def supports(self, cap: Capability) -> bool:
        """Convenience capability check used instead of ``if broker == ...``."""
        return cap in self.capabilities()

    @abstractmethod
    def close(self) -> None:
        """Tear down the underlying connection(s)."""
