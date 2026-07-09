"""Upstox DataProvider — adapts UpstoxBrokerGateway to domain DataProvider port."""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any, Callable

import pandas as pd

from domain.candles.historical import InstrumentRef
from domain.entities.market import MarketDepth, QuoteSnapshot
from domain.entities.options import FutureChain, OptionChain
from domain.instruments.instrument_id import InstrumentId
from domain.ports.protocols import DataProvider, SubscriptionHandle
from domain.provenance import DataProvenance, ProvenanceConfidence, SourceIdentity


class _UpstoxSubscriptionHandle(SubscriptionHandle):
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


class UpstoxDataProvider(DataProvider):
    """Adapts Upstox gateway methods (quote/history/depth) to InstrumentId API."""

    def __init__(self, gateway: Any, *, broker_id: str = "upstox") -> None:
        self._gw = gateway
        self._broker_id = broker_id or "upstox"

    @property
    def name(self) -> str:
        return self._broker_id

    def get_quote(self, instrument_id: InstrumentId) -> QuoteSnapshot | None:
        try:
            q = self._gw.quote(instrument_id.underlying, instrument_id.exchange)
            if q is None:
                return None
            if isinstance(q, QuoteSnapshot):
                return q
            return self._normalize_quote(q, instrument_id)
        except Exception:
            return None

    def get_quotes_batch(
        self, instrument_ids: list[InstrumentId]
    ) -> list[QuoteSnapshot | None]:
        """Batch quotes via native multi-key API when gateway supports quote_batch."""
        if not instrument_ids:
            return []
        quote_batch = getattr(self._gw, "quote_batch", None)
        if not callable(quote_batch):
            return [self.get_quote(i) for i in instrument_ids]

        # Group by exchange (Upstox keys encode segment; batch still groups for clarity)
        by_ex: dict[str, list[tuple[int, InstrumentId]]] = {}
        for i, iid in enumerate(instrument_ids):
            by_ex.setdefault(iid.exchange, []).append((i, iid))

        out: list[QuoteSnapshot | None] = [None] * len(instrument_ids)
        for exchange, items in by_ex.items():
            symbols = [iid.underlying for _, iid in items]
            try:
                raw_map = dict(quote_batch(symbols, exchange) or {})
            except Exception:
                raw_map = {}
            for idx, iid in items:
                raw = raw_map.get(iid.underlying)
                if raw is None:
                    out[idx] = self.get_quote(iid)
                    continue
                if isinstance(raw, QuoteSnapshot):
                    out[idx] = raw
                else:
                    out[idx] = self._normalize_quote(raw, iid)
        return out

    def get_history(
        self,
        instrument_id: InstrumentId,
        *,
        timeframe: str = "1D",
        lookback_days: int = 120,
        from_date: str | None = None,
        to_date: str | None = None,
    ) -> pd.DataFrame:
        try:
            hist = getattr(self._gw, "history", None)
            if not callable(hist):
                return pd.DataFrame()
            return hist(
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
        try:
            exp_str = expiry.strftime("%Y-%m-%d") if expiry else None
            chain_fn = getattr(self._gw, "option_chain", None)
            if not callable(chain_fn):
                return OptionChain(underlying=underlying.underlying, exchange="NFO", expiry="")
            raw = chain_fn(underlying.underlying, "NFO", exp_str)
            if isinstance(raw, OptionChain):
                return raw
            if isinstance(raw, dict):
                data = dict(raw)
                data.setdefault("underlying", underlying.underlying)
                data.setdefault("exchange", "NFO")
                return OptionChain.from_dict(data)
        except Exception:
            pass
        return OptionChain(underlying=underlying.underlying, exchange="NFO", expiry="")

    def get_future_chain(self, underlying: InstrumentId) -> FutureChain:
        try:
            fn = getattr(self._gw, "future_chain", None)
            if callable(fn):
                raw = fn(underlying.underlying, "NFO")
                if isinstance(raw, FutureChain):
                    return raw
                if isinstance(raw, dict):
                    return FutureChain.from_dict(raw)
        except Exception:
            pass
        return FutureChain(underlying=underlying.underlying, exchange="NFO")

    def subscribe(
        self,
        instrument_id: InstrumentId,
        callback: Callable[[InstrumentId, Any], None],
        *,
        depth: bool = False,
    ) -> SubscriptionHandle:
        try:
            stream = getattr(self._gw, "stream", None)
            if callable(stream):
                handle = stream(
                    instrument_id.underlying,
                    instrument_id.exchange,
                    callback,
                    depth=depth,
                )
                return _UpstoxSubscriptionHandle(stop_fn=getattr(handle, "stop", None))
        except Exception:
            pass
        return _UpstoxSubscriptionHandle()

    def unsubscribe(self, handle: SubscriptionHandle) -> None:
        handle.unsubscribe()

    def _normalize_quote(self, raw_quote: Any, instrument_id: InstrumentId) -> QuoteSnapshot:
        now = datetime.now(timezone.utc)
        if isinstance(raw_quote, dict):
            ltp = Decimal(str(raw_quote.get("last_price", raw_quote.get("ltp", 0)) or 0))
            bid = Decimal(str(raw_quote.get("bid", raw_quote.get("bid_price", 0)) or 0))
            ask = Decimal(str(raw_quote.get("ask", raw_quote.get("ask_price", 0)) or 0))
            volume = int(raw_quote.get("volume", 0) or 0)
        else:
            ltp = Decimal(str(getattr(raw_quote, "ltp", 0) or 0))
            bid = Decimal(str(getattr(raw_quote, "bid", 0) or 0))
            ask = Decimal(str(getattr(raw_quote, "ask", 0) or 0))
            volume = int(getattr(raw_quote, "volume", 0) or 0)
        return QuoteSnapshot(
            instrument=InstrumentRef(
                symbol=instrument_id.underlying,
                exchange=instrument_id.exchange,
            ),
            ltp=ltp,
            event_time=now,
            provenance=DataProvenance(
                source=SourceIdentity(broker_id=self._broker_id),
                fetched_at=now,
                request_id="",
                confidence=ProvenanceConfidence.AUTHORITATIVE,
            ),
            bid=bid if bid > 0 else None,
            ask=ask if ask > 0 else None,
            volume=volume,
        )
