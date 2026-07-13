"""Paper DataProvider — adapts PaperGateway to the domain DataProvider port."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable

import pandas as pd

from domain.candles.historical import HistoricalSeries, InstrumentRef
from domain.entities.market import MarketDepth, QuoteSnapshot
from domain.entities.options import FutureChain, OptionChain
from domain.instruments.instrument_id import InstrumentId
from domain.ports.protocols import DataProvider, SubscriptionHandle
from domain.ports.time_service import get_current_clock
from domain.provenance import DataProvenance, ProvenanceConfidence, SourceIdentity


class _PaperSubscriptionHandle(SubscriptionHandle):
    def __init__(self) -> None:
        self._active = True

    @property
    def is_active(self) -> bool:
        return self._active

    def unsubscribe(self) -> None:
        self._active = False


class PaperDataProvider(DataProvider):
    """Adapts ``PaperGateway`` to ``DataProvider`` for the public SDK."""

    def __init__(self, gateway: Any) -> None:
        self._gw = gateway

    @property
    def name(self) -> str:
        return "paper"

    def get_quote(self, instrument_id: InstrumentId) -> QuoteSnapshot | None:
        try:
            q = self._gw.quote(instrument_id.underlying, instrument_id.exchange)
            if q is None:
                return None
            if isinstance(q, QuoteSnapshot):
                return q
            # Paper Quote entity → QuoteSnapshot for Instrument state
            return QuoteSnapshot(
                instrument=InstrumentRef(
                    symbol=instrument_id.underlying, exchange=instrument_id.exchange
                ),
                ltp=q.ltp,
                event_time=get_current_clock().now(),
                provenance=DataProvenance(
                    source=SourceIdentity(broker_id="paper"),
                    fetched_at=get_current_clock().now(),
                    request_id="paper",
                    confidence=ProvenanceConfidence.AUTHORITATIVE,
                ),
                open=getattr(q, "open", None) or getattr(q, "open_", None),
                high=getattr(q, "high", None),
                low=getattr(q, "low", None),
                close=getattr(q, "close", None),
                bid=getattr(q, "bid", None),
                ask=getattr(q, "ask", None),
                volume=int(getattr(q, "volume", 0) or 0),
            )
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
        # PaperGateway.history(symbol, exchange=..., timeframe=..., lookback_days=...)
        # (historically this used wrong kwargs and silently returned empty frames)
        try:
            df = self._gw.history(
                instrument_id.underlying,
                exchange=instrument_id.exchange,
                timeframe=timeframe,
                lookback_days=lookback_days,
                from_date=from_date,
                to_date=to_date,
            )
            if df is None:
                return pd.DataFrame()
            return df
        except Exception:
            return pd.DataFrame()

    def get_history_series(
        self,
        instrument_id: InstrumentId,
        *,
        timeframe: str = "1D",
        lookback_days: int = 120,
        from_date: str | None = None,
        to_date: str | None = None,
    ) -> HistoricalSeries:
        ref = InstrumentRef(
            symbol=instrument_id.underlying, exchange=instrument_id.exchange
        )
        df = self.get_history(
            instrument_id,
            timeframe=timeframe,
            lookback_days=lookback_days,
            from_date=from_date,
            to_date=to_date,
        )
        if df is None or getattr(df, "empty", True):
            return HistoricalSeries(
                bars=[],
                coverage=None,
                instrument=ref,
                timeframe=timeframe,
            )
        return HistoricalSeries.from_broker_df(
            df,
            ref,
            timeframe,
            broker_id="paper",
            request_id="paper.history",
        )

    def get_depth(self, instrument_id: InstrumentId) -> MarketDepth | None:
        try:
            return self._gw.depth(instrument_id.underlying, instrument_id.exchange)
        except Exception:
            return None

    def subscribe(
        self,
        instrument_id: InstrumentId,
        callback: Callable[[InstrumentId, Any], None],
        *,
        depth: bool = False,
    ) -> SubscriptionHandle:
        """Paper subscribe: deliver one snapshot so Instrument state updates."""
        del depth  # paper has no separate depth stream
        handle = _PaperSubscriptionHandle()
        try:
            quote = self.get_quote(instrument_id)
            if quote is not None:
                callback(instrument_id, quote)
        except Exception:
            pass
        return handle

    def get_option_chain(
        self, instrument_id: InstrumentId, expiry: str | None = None
    ) -> OptionChain | None:
        try:
            return self._gw.option_chain(instrument_id.underlying, expiry=expiry)
        except Exception:
            return None

    def get_future_chain(self, instrument_id: InstrumentId) -> FutureChain | None:
        try:
            return self._gw.future_chain(instrument_id.underlying)
        except Exception:
            return None
