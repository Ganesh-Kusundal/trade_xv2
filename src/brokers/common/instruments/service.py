"""BrokerInstrumentService — common port every broker implements.

Instrument loading and symbol→wire-id mapping are internal to each broker.
Gateways call ``load`` / ``resolve`` / ``search`` with canonical symbols only;
``resolve_ref`` returns an opaque :class:`BrokerWireRef` consumed exclusively
by the broker connection when building HTTP / WebSocket payloads.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from brokers.common.instruments.carrier import BrokerWireRef, LoadStats, ResolvedInstrument


@runtime_checkable
class BrokerInstrumentService(Protocol):
    """Per-broker instrument master + security mapping."""

    def load(
        self,
        source: str | None = None,
        *,
        force_refresh: bool = False,
    ) -> LoadStats:
        """Load / refresh the instrument master into the in-memory resolver."""
        ...

    def resolve(self, symbol: str, exchange: str) -> ResolvedInstrument:
        """Resolve to a canonical record (no wire identifiers)."""
        ...

    def resolve_ref(
        self,
        symbol: str,
        exchange: str,
        *,
        expected_segment: str | None = None,
    ) -> BrokerWireRef:
        """Resolve to an opaque broker-wire reference for payload builders.

        Gateways must not call this — only the broker connection / adapters.
        """
        ...

    def search(self, query: str, *, limit: int = 20) -> list[dict]:
        """Prefix / substring search returning canonical dicts (no wire ids)."""
        ...

    def stats(self) -> dict:
        """Observability snapshot (loaded flag, counts, …)."""
        ...

    def is_loaded(self) -> bool:
        """True once a successful ``load`` has populated the resolver."""
        ...
