"""Market data composer — unified interface for historical data and streams.

Delegates to HistoricalDataCoordinator and StreamOrchestrator rather than
calling broker gateways directly. Ensures all market data operations have
proper routing, quota management, and provenance tracking.
"""

from __future__ import annotations

import logging
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from brokers.common.historical_coordinator import HistoricalDataCoordinator, HistoricalQuery
    from brokers.common.provenance import ProvenanceLedger
    from brokers.common.stream_orchestrator import StreamOrchestrator, SubscriptionRequest

from domain.candles.historical import HistoricalSeries

logger = logging.getLogger(__name__)


class MarketDataComposer:
    """High-level market data interface for application code.

    Usage::

        composer = MarketDataComposer(
            historical_coordinator=coordinator,
            stream_orchestrator=orchestrator,
        )

        # Fetch historical data with federation
        series, ledger = await composer.fetch_historical(query)

        # Subscribe to market stream
        sub_id = await composer.subscribe_market_stream(request)
    """

    def __init__(
        self,
        historical_coordinator: HistoricalDataCoordinator,
        stream_orchestrator: StreamOrchestrator,
    ) -> None:
        self._historical_coordinator = historical_coordinator
        self._stream_orchestrator = stream_orchestrator

    async def fetch_historical(
        self,
        query: HistoricalQuery,
    ) -> tuple[HistoricalSeries, ProvenanceLedger]:
        """Fetch historical bars with multi-broker federation.

        Delegates to HistoricalDataCoordinator which handles:
        - Chunk planning across brokers
        - Concurrent fetch with quota gating
        - Merge with conflict detection
        - Provenance ledger construction

        Parameters
        ----------
        query
            Historical query specifying instrument, timeframe, and date range.

        Returns
        -------
        tuple[HistoricalSeries, ProvenanceLedger]
            Merged historical series and complete provenance audit trail.

        Notes
        -----
        Always returns a result — uses degraded mode rather than raising
        when a source is partially unavailable. Check ``series.is_degraded``
        and ``ledger.degraded`` to detect incomplete data.
        """
        logger.info(
            "market_data.fetch_historical",
            extra={
                "instrument": str(query.instrument),
                "timeframe": query.timeframe,
                "from_date": query.from_date.isoformat(),
                "to_date": query.to_date.isoformat(),
            },
        )

        series, ledger = await self._historical_coordinator.fetch(query)

        logger.info(
            "market_data.fetch_historical.complete",
            extra={
                "instrument": str(query.instrument),
                "bar_count": series.bar_count,
                "degraded": series.is_degraded,
                "brokers_used": list(series.brokers_contributing()),
                "conflicts": len(ledger.conflicts),
            },
        )

        return series, ledger

    async def subscribe_market_stream(
        self,
        request: SubscriptionRequest,
    ) -> str:
        """Subscribe to market data stream via StreamOrchestrator.

        Delegates to StreamOrchestrator which handles:
        - Broker selection via policy
        - WebSocket lifecycle management
        - Reconnect with exponential backoff
        - Staleness detection and failover
        - Consumer fan-out with backpressure

        Parameters
        ----------
        request
            Subscription request specifying instruments, modes, and consumer.

        Returns
        -------
        str
            Subscription ID for later unsubscription.
        """
        logger.info(
            "market_data.subscribe_stream",
            extra={
                "stream_kind": request.stream_kind,
                "instrument_count": len(request.instruments),
                "allow_failover": request.allow_failover,
            },
        )

        sub_id = await self._stream_orchestrator.subscribe(request)

        logger.info(
            "market_data.subscribe_stream.complete",
            extra={"sub_id": sub_id},
        )

        return sub_id

    async def unsubscribe_market_stream(self, sub_id: str) -> None:
        """Unsubscribe from a market data stream.

        Parameters
        ----------
        sub_id
            Subscription ID returned from subscribe_market_stream.
        """
        await self._stream_orchestrator.unsubscribe(sub_id)
        logger.info("market_data.unsubscribe_stream", extra={"sub_id": sub_id})

    def get_stream_health(self, session_id: str) -> Any:
        """Get health state of a stream session.

        Parameters
        ----------
        session_id
            Session ID to query.

        Returns
        -------
        StreamHealth | None
            Current health state, or None if session not found.
        """
        return self._stream_orchestrator.session_health(session_id)

    def get_all_stream_sessions(self) -> list[Any]:
        """Get snapshot of all active stream sessions.

        Returns
        -------
        list[StreamSession]
            All current sessions with health state.
        """
        return self._stream_orchestrator.all_sessions()
