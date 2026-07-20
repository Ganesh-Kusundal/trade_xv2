"""Dhan DataProvider — adapts DhanWireAdapter to the domain DataProvider port.

Used by ``tradex.connect("dhan", mode="market"|"trade")`` so
``session.universe.equity(...).refresh()`` works without importing the gateway.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any, Callable

import pandas as pd

from domain.candles.historical import InstrumentRef, HistoricalSeries
from domain.entities.market import MarketDepth, QuoteSnapshot
from domain.entities.options import FutureChain, OptionChain
from domain.instruments.instrument_id import InstrumentId
from domain.ports.protocols import DataProvider, SubscriptionHandle
from domain.ports.time_service import get_current_clock
from domain.provenance import DataProvenance, ProvenanceConfidence, SourceIdentity


class _DhanSubscriptionHandle(SubscriptionHandle):
    def __init__(
        self,
        stop_fn: Callable[[], None] | None = None,
        is_connected_fn: Callable[[], bool] | None = None,
    ) -> None:
        self._active = True
        self._stop = stop_fn
        self._is_connected_fn = is_connected_fn

    @property
    def is_active(self) -> bool:
        return self._active

    @property
    def is_connected(self) -> bool:
        """Best-effort live-connection check (for probes/health checks)."""
        return bool(self._is_connected_fn()) if self._is_connected_fn is not None else False

    def unsubscribe(self) -> None:
        self._active = False
        if self._stop is not None:
            self._stop()


class DhanDataProvider(DataProvider):
    """Adapts ``DhanWireAdapter`` to domain ``DataProvider`` (InstrumentId API)."""

    def __init__(self, gateway: Any, *, broker_id: str = "dhan") -> None:
        self._gw = gateway
        self._broker_id = broker_id or "dhan"

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

    def get_quotes_batch(self, instrument_ids: list[InstrumentId]) -> list[QuoteSnapshot | None]:
        """Batch quotes; groups by exchange and uses gateway quote_batch when present."""
        if not instrument_ids:
            return []
        # Group by exchange for broker batch APIs
        by_ex: dict[str, list[tuple[int, InstrumentId]]] = {}
        for i, iid in enumerate(instrument_ids):
            by_ex.setdefault(iid.exchange, []).append((i, iid))

        out: list[QuoteSnapshot | None] = [None] * len(instrument_ids)
        quote_batch = getattr(self._gw, "quote_batch", None)
        ltp_batch = getattr(self._gw, "ltp_batch", None)

        for exchange, items in by_ex.items():
            symbols = [iid.underlying for _, iid in items]
            raw_map: dict[str, Any] = {}
            if callable(quote_batch):
                try:
                    raw_map = dict(quote_batch(symbols, exchange) or {})
                except Exception:
                    raw_map = {}
            if not raw_map and callable(ltp_batch):
                try:
                    ltps = dict(ltp_batch(symbols, exchange) or {})
                    raw_map = {sym: {"last_price": ltps[sym]} for sym in ltps}
                except Exception:
                    raw_map = {}
            for idx, iid in items:
                raw = raw_map.get(iid.underlying) or raw_map.get(str(iid))
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
    ) -> HistoricalSeries:
        """Return canonical ``HistoricalSeries`` (SSOT at broker→app boundary)."""
        return self.get_history_series(
            instrument_id,
            timeframe=timeframe,
            lookback_days=lookback_days,
            from_date=from_date,
            to_date=to_date,
        )

    def _history_dataframe(
        self,
        instrument_id: InstrumentId,
        *,
        timeframe: str = "1D",
        lookback_days: int = 120,
        from_date: str | None = None,
        to_date: str | None = None,
    ) -> pd.DataFrame:
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
            # ponytail: re-raise broker/provider errors so callers can see
            # entitlement/param failures (e.g. DH-905) instead of silent empty.
            # A genuinely empty payload (df with no rows) is handled by the
            # caller, not here.
            raise

    def get_history_series(
        self,
        instrument_id: InstrumentId,
        *,
        timeframe: str = "1D",
        lookback_days: int = 120,
        from_date: str | None = None,
        to_date: str | None = None,
    ) -> HistoricalSeries:
        ref = InstrumentRef(symbol=instrument_id.underlying, exchange=instrument_id.exchange)
        df = self._history_dataframe(
            instrument_id,
            timeframe=timeframe,
            lookback_days=lookback_days,
            from_date=from_date,
            to_date=to_date,
        )
        if df is None or getattr(df, "empty", True):
            return HistoricalSeries(bars=[], coverage=None, instrument=ref, timeframe=timeframe)
        return HistoricalSeries.from_broker_df(
            df,
            ref,
            timeframe,
            broker_id=self._broker_id,
            request_id="dhan.history",
        )

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
            # Index underlyings trade options on NFO (equity on NSE)
            exch = "NFO"
            if underlying.exchange in {"NFO", "MCX", "BFO"}:
                exch = underlying.exchange
            raw = self._gw.option_chain(underlying.underlying, exch, exp_str)
            return self._normalize_option_chain(raw, underlying, exp_str)
        except Exception:
            return OptionChain(
                underlying=underlying.underlying,
                exchange="NFO",
                expiry="",
            )

    def get_future_chain(self, underlying: InstrumentId) -> FutureChain:
        try:
            raw = self._gw.future_chain(underlying.underlying, "NFO")
            if isinstance(raw, FutureChain):
                return raw
            # Best-effort empty when gateway returns non-VO
            return FutureChain(
                underlying=underlying.underlying,
                exchange="NFO",
            )
        except Exception:
            return FutureChain(underlying=underlying.underlying, exchange="NFO")

    def _normalize_option_chain(
        self,
        raw: Any,
        underlying: InstrumentId,
        exp_str: str | None,
    ) -> OptionChain:
        if isinstance(raw, OptionChain):
            return raw
        if isinstance(raw, dict):
            # Ensure identity fields for domain VO
            data = dict(raw)
            data.setdefault("underlying", underlying.underlying)
            data.setdefault("exchange", data.get("exchange") or "NFO")
            if exp_str and not data.get("expiry"):
                data["expiry"] = exp_str
            return OptionChain.from_dict(data)
        return OptionChain(
            underlying=underlying.underlying,
            exchange="NFO",
            expiry=exp_str or "",
        )

    def subscribe(
        self,
        instrument_id: InstrumentId,
        callback: Callable[[InstrumentId, Any], None],
        *,
        depth: bool = False,
    ) -> SubscriptionHandle:
        """Subscribe via gateway.stream; normalize ticks to QuoteSnapshot.

        Gateway signature: ``stream(symbol, exchange, mode=..., on_tick=...)``.
        Instrument layer only applies QuoteSnapshot / MarketDepth to state.
        """
        # "DEPTH" is not a valid Dhan feed mode (only LTP/QUOTE/FULL) — using
        # it silently produced plain quotes with bid=None/ask=None. "FULL"
        # is the mode that actually carries bid/ask.
        mode = "FULL" if depth else "QUOTE"

        def _on_tick(payload: Any) -> None:
            try:
                if isinstance(payload, QuoteSnapshot):
                    snap = payload
                elif isinstance(payload, MarketDepth):
                    callback(instrument_id, payload)
                    return
                else:
                    snap = self._normalize_quote(payload, instrument_id)
                callback(instrument_id, snap)
            except Exception:
                # Never break the feed thread from user/provider errors
                pass

        try:
            from brokers.dhan.data.instrument_adapter import to_dhan_symbol

            handle = self._gw.stream(
                to_dhan_symbol(instrument_id),
                instrument_id.exchange,
                mode=mode,
                on_tick=_on_tick,
            )
            stop = getattr(handle, "stop", None) or getattr(handle, "disconnect", None)
            return _DhanSubscriptionHandle(
                stop_fn=stop if callable(stop) else None,
                is_connected_fn=lambda: getattr(handle, "is_connected", False),
            )
        except Exception:
            return _DhanSubscriptionHandle()

    def unsubscribe(self, handle: SubscriptionHandle) -> None:
        handle.unsubscribe()

    def _normalize_quote(self, raw_quote: Any, instrument_id: InstrumentId) -> QuoteSnapshot:
        now = get_current_clock().now()
        if isinstance(raw_quote, dict):
            ltp = Decimal(str(raw_quote.get("last_price", 0)))
            bid = Decimal(str(raw_quote.get("bid_price", raw_quote.get("best_bid", 0))))
            ask = Decimal(str(raw_quote.get("ask_price", raw_quote.get("best_ask", 0))))
            high = Decimal(str(raw_quote.get("high", 0)))
            low = Decimal(str(raw_quote.get("low", 0)))
            open_ = Decimal(str(raw_quote.get("open", 0)))
            close = Decimal(str(raw_quote.get("close", raw_quote.get("prev_close", 0))))
            volume = int(raw_quote.get("volume", 0) or 0)
            oi = int(raw_quote.get("oi", 0) or 0)
        else:
            ltp = Decimal(str(getattr(raw_quote, "ltp", 0) or 0))
            bid = Decimal(str(getattr(raw_quote, "bid", 0) or 0))
            ask = Decimal(str(getattr(raw_quote, "ask", 0) or 0))
            high = Decimal(str(getattr(raw_quote, "high", 0) or 0))
            low = Decimal(str(getattr(raw_quote, "low", 0) or 0))
            open_ = Decimal(str(getattr(raw_quote, "open", 0) or 0))
            close = Decimal(str(getattr(raw_quote, "close", 0) or 0))
            volume = int(getattr(raw_quote, "volume", 0) or 0)
            oi = int(getattr(raw_quote, "oi", 0) or 0)

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
            high=high if high > 0 else None,
            low=low if low > 0 else None,
            open=open_ if open_ > 0 else None,
            close=close if close > 0 else None,
            volume=volume,
            oi=oi,
        )
