from __future__ import annotations

"""Upstox -> domain DataProvider adapter (broker as a plugin).

Wraps ``brokers.upstox.gateway.UpstoxBrokerGateway`` and normalizes its
outputs into the domain ``DataProvider`` protocol.
"""

from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from domain.candles.historical import InstrumentRef
from domain.entities.market import QuoteSnapshot
from domain.provenance import DataProvenance, ProvenanceConfidence, SourceIdentity
from brokers.common.adapter_base import BaseDataAdapter

if TYPE_CHECKING:
    from domain.instruments.instrument_id import InstrumentId


class UpstoxDataAdapter(BaseDataAdapter):
    """Adapts an Upstox ``UpstoxBrokerGateway`` to the domain ``DataProvider`` port."""

    def __init__(self, gateway: Any, *, broker_id: str = "upstox") -> None:
        super().__init__(gateway, broker_id=broker_id)

    def _get_depth_stream_method(self) -> str | None:
        """Upstox uses stream_depth for depth streaming."""
        return "stream_depth"

    def get_quote_snapshot(self, instrument_id: "InstrumentId") -> QuoteSnapshot | None:
        """Fetch LTP via gateway.ltp() and build a lightweight QuoteSnapshot.

        This is the fastest path when only the last-traded price is needed.
        """
        ltp = self._gw.ltp(instrument_id.underlying, instrument_id.exchange)
        ts = datetime.now(tz=timezone.utc)
        provenance = DataProvenance(
            source=SourceIdentity(broker_id=self._broker_id),
            fetched_at=ts,
            request_id="upstox-adapter-ltp",
            confidence=ProvenanceConfidence.AUTHORITATIVE,
            provider_timestamp=ts,
        )
        return QuoteSnapshot(
            instrument=InstrumentRef(
                symbol=instrument_id.underlying,
                exchange=instrument_id.exchange,
            ),
            ltp=ltp,
            event_time=ts,
            provenance=provenance,
        )
