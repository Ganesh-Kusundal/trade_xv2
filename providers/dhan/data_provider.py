"""Dhan DataProvider — implements the DataProvider port.

Wraps DhanGateway and normalizes its outputs into domain objects.
The user layer never imports this module directly.
"""

from __future__ import annotations

import warnings
from datetime import date
from typing import TYPE_CHECKING, Any, Callable

import pandas as pd

from domain.entities.market import MarketDepth, QuoteSnapshot
from domain.entities.options import FutureChain, OptionChain
from domain.instruments.instrument_id import InstrumentId
from domain.ports.protocols import DataProvider, SubscriptionHandle

if TYPE_CHECKING:
    pass


class _DhanSubscriptionHandle(SubscriptionHandle):
    """Subscription handle wrapping Dhan's stream handle."""

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


class DhanDataProvider(DataProvider):
    """Adapts DhanGateway to the DataProvider port.

    This is the ONLY place where Dhan's gateway meets the domain.
    The public Instrument API never imports this module.

    .. deprecated::
        Phase 9.3 of the Instrument-Centric SDK Redesign. Data access is being
        consolidated into a unified ``DhanBrokerAdapter``. Prefer the broker
        adapter exposed via ``BrokerSession``.
    """

    def __init__(self, gateway: Any) -> None:
        warnings.warn(
            "providers.dhan.data_provider.DhanDataProvider is deprecated; data "
            "access is moving into the unified broker adapter "
            "(brokers.dhan.adapter). See Instrument-Centric SDK Redesign, Phase 9.3.",
            DeprecationWarning,
            stacklevel=2,
        )
        self._gw = gateway

    @property
    def name(self) -> str:
        return "dhan"

    def get_quote(self, instrument_id: InstrumentId) -> QuoteSnapshot | None:
        """Fetch latest quote from Dhan gateway."""
        try:
            q = self._gw.quote(instrument_id.underlying, instrument_id.exchange)
            if q is None:
                return None
            return self._normalize_quote(q, instrument_id)
        except Exception:
            return None

    def get_history(
        self,
        instrument_id: InstrumentId,
        *,
        timeframe: str = "1D",
        lookback_days: int = 120,
        from_date: str | None = None,
        to_date: str | None = None,
    ) -> pd.DataFrame:
        """Fetch historical OHLCV from Dhan gateway."""
        try:
            return self._gw.history(
                instrument_id.underlying,
                instrument_id.exchange,
                timeframe,
                lookback_days,
                from_date,
                to_date,
            )
        except Exception:
            return pd.DataFrame()

    def get_depth(self, instrument_id: InstrumentId) -> MarketDepth | None:
        """Fetch market depth from Dhan gateway."""
        try:
            return self._gw.depth(instrument_id.underlying, instrument_id.exchange)
        except Exception:
            return None

    def get_option_chain(
        self,
        underlying: InstrumentId,
        *,
        expiry: date | None = None,
    ) -> OptionChain:
        """Fetch option chain from Dhan gateway."""
        try:
            exp_str = expiry.strftime("%Y-%m-%d") if expiry else None
            return self._gw.option_chain(underlying.underlying, "NFO", exp_str)
        except Exception:
            return OptionChain(underlying="", exchange="", expiry="")

    def get_future_chain(self, underlying: InstrumentId) -> FutureChain:
        """Fetch futures chain from Dhan gateway."""
        try:
            return self._gw.future_chain(underlying.underlying, "NFO")
        except Exception:
            return FutureChain(underlying="", exchange="")

    def subscribe(
        self,
        instrument_id: InstrumentId,
        callback: Callable[[InstrumentId, Any], None],
        *,
        depth: bool = False,
    ) -> SubscriptionHandle:
        """Subscribe to live market data from Dhan."""
        try:
            handle = self._gw.stream(
                instrument_id.underlying,
                instrument_id.exchange,
                callback,
                depth=depth,
            )
            return _DhanSubscriptionHandle(stop_fn=getattr(handle, "stop", None))
        except Exception:
            return _DhanSubscriptionHandle()

    def unsubscribe(self, handle: SubscriptionHandle) -> None:
        """Cancel a subscription."""
        handle.unsubscribe()

    def _normalize_quote(self, raw_quote: Any, instrument_id: InstrumentId) -> QuoteSnapshot:
        """Convert Dhan's quote format to domain QuoteSnapshot."""
        from datetime import datetime

        from domain.candles.historical import InstrumentRef
        from domain.provenance import DataProvenance, ProvenanceConfidence, SourceIdentity

        # Handle both dict and object responses
        if isinstance(raw_quote, dict):
            ltp = Decimal(str(raw_quote.get("last_price", 0)))
            bid = Decimal(str(raw_quote.get("bid_price", raw_quote.get("best_bid", 0))))
            ask = Decimal(str(raw_quote.get("ask_price", raw_quote.get("best_ask", 0))))
            high = Decimal(str(raw_quote.get("high", 0)))
            low = Decimal(str(raw_quote.get("low", 0)))
            open_ = Decimal(str(raw_quote.get("open", 0)))
            close = Decimal(str(raw_quote.get("close", raw_quote.get("prev_close", 0))))
            volume = int(raw_quote.get("volume", 0))
        else:
            ltp = Decimal(str(getattr(raw_quote, "ltp", 0)))
            bid = Decimal(str(getattr(raw_quote, "bid", 0)))
            ask = Decimal(str(getattr(raw_quote, "ask", 0)))
            high = Decimal(str(getattr(raw_quote, "high", 0)))
            low = Decimal(str(getattr(raw_quote, "low", 0)))
            open_ = Decimal(str(getattr(raw_quote, "open", 0)))
            close = Decimal(str(getattr(raw_quote, "close", 0)))
            volume = int(getattr(raw_quote, "volume", 0))

        return QuoteSnapshot(
            instrument=InstrumentRef(
                symbol=instrument_id.underlying,
                exchange=instrument_id.exchange,
            ),
            ltp=ltp,
            event_time=datetime.now(),
            provenance=DataProvenance(
                source=SourceIdentity(broker_id="dhan"),
                fetched_at=datetime.now(),
                request_id="",
                confidence=ProvenanceConfidence.AUTHORITATIVE,
            ),
            bid=bid if bid > 0 else None,
            ask=ask if ask > 0 else None,
            high=high,
            low=low,
            open=open_,
            close=close,
            volume=volume,
        )


# Need Decimal for normalization
from decimal import Decimal
