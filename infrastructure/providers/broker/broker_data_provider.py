"""BrokerDataProvider — wraps existing MarketDataGateway behind DataProvider protocol.

This is the primary adapter that bridges the existing broker infrastructure
(Dhan, Upstox, Paper) to the new Instrument-Centric Architecture.  It wraps
the MarketDataGateway ABC and translates InstrumentId-based calls to the
symbol+exchange-based gateway methods.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import date
from typing import Any

import pandas as pd

from domain.entities.options import FutureChain, OptionChain
from domain.entities.market import MarketDepth, QuoteSnapshot
from domain.instrument_id import InstrumentId
from domain.provenance import DataProvenance, SourceIdentity
from domain.providers.protocols import Subscription

logger = logging.getLogger(__name__)


class _BrokerSubscription:
    """Subscription handle wrapping broker stream handle."""

    def __init__(self, stream_handle: Any, instrument_id: InstrumentId) -> None:
        self._handle = stream_handle
        self._instrument_id = instrument_id
        self._active = True

    @property
    def is_active(self) -> bool:
        return self._active

    def unsubscribe(self) -> None:
        if self._active and self._handle is not None:
            try:
                if hasattr(self._handle, "disconnect"):
                    self._handle.disconnect()
                elif hasattr(self._handle, "close"):
                    self._handle.close()
            except Exception as exc:
                logger.warning("Error unsubscribing %s: %s", self._instrument_id, exc)
            self._active = False


class BrokerDataProvider:
    """DataProvider implementation backed by a live broker connection.

    Wraps the existing ``MarketDataGateway`` ABC (DhanGateway, UpstoxGateway)
    behind the new ``DataProvider`` protocol.  InstrumentId-based calls are
    translated to symbol+exchange-based gateway methods.

    Parameters
    ----------
    gateway:
        A concrete ``MarketDataGateway`` instance (Dhan, Upstox, Paper).
    broker_name:
        Identifier for provenance tracking (e.g., ``"dhan"``, ``"upstox"``).
    """

    def __init__(self, gateway: Any, broker_name: str = "broker") -> None:
        self._gateway = gateway
        self._broker_name = broker_name

    @property
    def name(self) -> str:
        return self._broker_name

    def get_quote(self, instrument_id: InstrumentId) -> QuoteSnapshot | None:
        """Get latest quote via gateway.quote()."""
        try:
            quote = self._gateway.quote(
                symbol=instrument_id.underlying,
                exchange=instrument_id.exchange,
            )
            if quote is None:
                return None
            return QuoteSnapshot(
                instrument=instrument_id,
                ltp=quote.ltp,
                event_time=quote.timestamp or pd.Timestamp.now(),
                provenance=DataProvenance.now(
                    broker_id=self._broker_name,
                    request_id=f"quote:{instrument_id}",
                ),
                open=quote.open,
                high=quote.high,
                low=quote.low,
                close=quote.close,
                volume=quote.volume,
                change_pct=quote.change,
                bid=quote.bid,
                ask=quote.ask,
            )
        except Exception as exc:
            logger.warning("get_quote(%s) failed: %s", instrument_id, exc)
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
        """Get historical OHLCV via gateway.history()."""
        return self._gateway.history(
            symbol=instrument_id.underlying,
            exchange=instrument_id.exchange,
            timeframe=timeframe,
            lookback_days=lookback_days,
            from_date=from_date,
            to_date=to_date,
        )

    def get_depth(self, instrument_id: InstrumentId) -> MarketDepth | None:
        """Get market depth via gateway.depth()."""
        try:
            return self._gateway.depth(
                symbol=instrument_id.underlying,
                exchange=instrument_id.exchange,
            )
        except Exception as exc:
            logger.warning("get_depth(%s) failed: %s", instrument_id, exc)
            return None

    def get_option_chain(
        self,
        underlying: InstrumentId,
        *,
        expiry: date | None = None,
    ) -> OptionChain:
        """Get option chain via gateway.option_chain()."""
        expiry_str = expiry.strftime("%Y-%m-%d") if expiry else None
        return self._gateway.option_chain(
            underlying=underlying.underlying,
            exchange=underlying.exchange,
            expiry=expiry_str,
        )

    def get_future_chain(self, underlying: InstrumentId) -> FutureChain:
        """Get futures chain via gateway.future_chain()."""
        return self._gateway.future_chain(
            underlying=underlying.underlying,
            exchange=underlying.exchange,
        )

    def subscribe(
        self,
        instrument_id: InstrumentId,
        callback: Callable[[InstrumentId, Any], None],
        *,
        depth: bool = False,
    ) -> Subscription:
        """Subscribe to live market data via gateway.stream().

        Wraps the broker's stream handle in a Subscription object.
        """
        mode = "DEPTH" if depth else "QUOTE"

        def _on_tick(tick: dict) -> None:
            try:
                from decimal import Decimal

                ltp = Decimal(str(tick.get("ltp", 0)))
                quote = QuoteSnapshot(
                    instrument=instrument_id,
                    ltp=ltp,
                    event_time=pd.Timestamp.now(),
                    provenance=DataProvenance.now(
                        broker_id=self._broker_name,
                        request_id=f"stream:{instrument_id}",
                    ),
                    volume=int(tick.get("volume", 0)),
                    bid=Decimal(str(tick["bid"])) if tick.get("bid") else None,
                    ask=Decimal(str(tick["ask"])) if tick.get("ask") else None,
                    open=Decimal(str(tick.get("open", 0))),
                    high=Decimal(str(tick.get("high", 0))),
                    low=Decimal(str(tick.get("low", 0))),
                    close=Decimal(str(tick.get("close", 0))),
                )
                callback(instrument_id, quote)
            except Exception as exc:
                logger.warning("Stream callback error for %s: %s", instrument_id, exc)

        handle = self._gateway.stream(
            symbol=instrument_id.underlying,
            exchange=instrument_id.exchange,
            mode=mode,
            on_tick=_on_tick,
        )
        return _BrokerSubscription(handle, instrument_id)

    def unsubscribe(self, subscription: Subscription) -> None:
        """Cancel a subscription."""
        subscription.unsubscribe()

    def history_batch(
        self,
        instrument_ids: list[InstrumentId],
        *,
        timeframe: str = "1D",
        lookback_days: int = 120,
    ) -> pd.DataFrame:
        """Load historical OHLCV for multiple instruments via gateway.history_batch()."""
        symbols = [iid.underlying for iid in instrument_ids]
        exchange = instrument_ids[0].exchange if instrument_ids else "NSE"
        return self._gateway.history_batch(
            symbols=symbols,
            exchange=exchange,
            timeframe=timeframe,
            lookback_days=lookback_days,
        )

    def list_instruments(self, exchange: str | None = None) -> list[InstrumentId]:
        """List known instruments via gateway.load_instruments() + search.

        Note: This is a best-effort implementation.  The gateway doesn't
        have a direct 'list all instruments' method, so we use the
        instrument search with an empty query.
        """
        try:
            results = self._gateway.search(query="")
            instruments = []
            for r in results:
                try:
                    iid = InstrumentId(
                        exchange=r.get("exchange", exchange or "NSE"),
                        underlying=r.get("symbol", ""),
                    )
                    instruments.append(iid)
                except (ValueError, KeyError):
                    continue
            return instruments
        except Exception as exc:
            logger.debug("list_instruments failed: %s", exc)
            return []
