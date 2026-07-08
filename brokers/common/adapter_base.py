from __future__ import annotations

"""Base adapter — shared implementation for broker DataProvider adapters.

Extracts the ~90% duplicated code from DhanDataAdapter and UpstoxDataAdapter
into a single base class. Broker-specific adapters subclass this and override
only the gateway-specific method mappings.
"""

from datetime import datetime, timezone
from decimal import Decimal
from typing import TYPE_CHECKING, Any

import pandas as pd

from domain.entities.market import MarketDepth, QuoteSnapshot
from domain.entities.options import FutureChain, OptionChain
from domain.candles.historical import InstrumentRef
from domain.provenance import DataProvenance, ProvenanceConfidence, SourceIdentity
from domain.ports.protocols import DataProvider, SubscriptionHandle

if TYPE_CHECKING:
    from collections.abc import Callable
    from datetime import date

    from domain.entities.market import Quote
    from domain.instruments.instrument_id import InstrumentId


class GatewaySubscription(SubscriptionHandle):
    """Subscription handle returned by the adapter's subscribe()."""

    def __init__(self, stop_fn: Callable[[], None] | None = None) -> None:
        self._active = True
        self._stop = stop_fn

    @property
    def is_active(self) -> bool:
        return self._active

    def unsubscribe(self) -> None:
        self._active = False
        if self._stop is not None:
            self._stop()


class BaseDataAdapter(DataProvider):
    """Base adapter implementing DataProvider protocol.

    Subclass this and override gateway-specific method mappings.
    The normalization helpers (_quote_to_snapshot, _depth_to_snapshot)
    are shared across all broker adapters.
    """

    def __init__(self, gateway: Any, *, broker_id: str) -> None:
        self._gw = gateway
        self._broker_id = broker_id

    # ── DataProvider port (shared implementation) ───────────────────

    @property
    def name(self) -> str:
        return f"{self._broker_id}-adapter"

    def get_quote(self, instrument_id: "InstrumentId") -> QuoteSnapshot | None:
        q = self._gw.quote(instrument_id.underlying, instrument_id.exchange)
        if q is None:
            return None
        return self._quote_to_snapshot(q, instrument_id)

    def get_history(
        self,
        instrument_id: "InstrumentId",
        *,
        timeframe: str = "1D",
        lookback_days: int = 120,
        from_date: str | None = None,
        to_date: str | None = None,
    ) -> pd.DataFrame:
        return self._gw.history(
            instrument_id.underlying,
            instrument_id.exchange,
            timeframe,
            lookback_days,
            from_date,
            to_date,
        )

    def get_depth(self, instrument_id: "InstrumentId") -> MarketDepth | None:
        return self._gw.depth(instrument_id.underlying, instrument_id.exchange)

    def get_option_chain(
        self,
        underlying: "InstrumentId",
        *,
        expiry: "date | None" = None,
    ) -> OptionChain:
        exp_str = expiry.strftime("%Y-%m-%d") if expiry is not None else None
        return self._gw.option_chain(underlying.underlying, "NFO", exp_str)

    def get_future_chain(self, underlying: "InstrumentId") -> FutureChain:
        return self._gw.future_chain(underlying.underlying, "NFO")

    def subscribe(
        self,
        instrument_id: "InstrumentId",
        callback: "Callable[[InstrumentId, QuoteSnapshot], None]",
        *,
        depth: bool = False,
    ) -> SubscriptionHandle:
        symbol, exchange = instrument_id.underlying, instrument_id.exchange
        # Subclasses can override _get_depth_stream_method() to customize
        depth_method = self._get_depth_stream_method()
        if depth and depth_method and hasattr(self._gw, depth_method):
            def _on_depth(md: MarketDepth) -> None:
                callback(instrument_id, self._depth_to_snapshot(md, instrument_id))

            getattr(self._gw, depth_method)(symbol, exchange, on_depth=_on_depth)
            return GatewaySubscription(None)

        # Default: one-shot snapshot
        q = self._gw.quote(symbol, exchange)
        if q is not None:
            callback(instrument_id, self._quote_to_snapshot(q, instrument_id))
        return GatewaySubscription(None)

    def unsubscribe(self, subscription: SubscriptionHandle) -> None:
        subscription.unsubscribe()

    def history_batch(
        self,
        instrument_ids: list["InstrumentId"],
        *,
        timeframe: str = "1D",
        lookback_days: int = 120,
    ) -> pd.DataFrame:
        frames = [
            self.get_history(i, timeframe=timeframe, lookback_days=lookback_days)
            for i in instrument_ids
        ]
        return pd.concat(frames) if frames else pd.DataFrame()

    def list_instruments(self, exchange: str | None = None) -> list["InstrumentId"]:
        return []  # Subclasses can override

    # ── Override points for subclasses ──────────────────────────────

    def _get_depth_stream_method(self) -> str | None:
        """Return the gateway method name for depth streaming.

        Override in subclasses if the gateway uses a different method name.
        Returns None to disable depth streaming.
        """
        return None

    # ── Normalization helpers (shared) ──────────────────────────────

    def _quote_to_snapshot(
        self, q: "Quote", instrument_id: "InstrumentId"
    ) -> QuoteSnapshot:
        ts = q.timestamp or datetime.now(tz=timezone.utc)
        provenance = DataProvenance(
            source=SourceIdentity(broker_id=self._broker_id),
            fetched_at=datetime.now(tz=timezone.utc),
            request_id=f"{self._broker_id}-adapter",
            confidence=ProvenanceConfidence.AUTHORITATIVE,
            provider_timestamp=ts,
        )
        return QuoteSnapshot(
            instrument=InstrumentRef(
                symbol=instrument_id.underlying,
                exchange=instrument_id.exchange,
            ),
            ltp=q.ltp,
            event_time=ts,
            provenance=provenance,
            open=q.open,
            high=q.high,
            low=q.low,
            close=q.close,
            volume=q.volume,
            change_pct=(
                (q.change / q.close) * Decimal("100")
                if q.close and q.close != Decimal("0")
                else Decimal("0")
            ),
            bid=q.bid,
            ask=q.ask,
        )

    def _depth_to_snapshot(
        self, md: MarketDepth, instrument_id: "InstrumentId"
    ) -> QuoteSnapshot:
        best_bid = md.bids[0].price if md.bids else None
        best_ask = md.asks[0].price if md.asks else None
        ts = md.timestamp or datetime.now(tz=timezone.utc)
        provenance = DataProvenance(
            source=SourceIdentity(broker_id=self._broker_id),
            fetched_at=datetime.now(tz=timezone.utc),
            request_id=f"{self._broker_id}-adapter-depth",
            confidence=ProvenanceConfidence.AUTHORITATIVE,
            provider_timestamp=ts,
        )
        return QuoteSnapshot(
            instrument=InstrumentRef(
                symbol=instrument_id.underlying,
                exchange=instrument_id.exchange,
            ),
            ltp=best_ask or best_bid or Decimal("0"),
            event_time=ts,
            provenance=provenance,
            bid=best_bid,
            ask=best_ask,
        )
