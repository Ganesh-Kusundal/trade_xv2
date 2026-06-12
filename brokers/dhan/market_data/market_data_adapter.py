"""Market data adapter for Dhan."""

from __future__ import annotations

from datetime import date
from typing import Any

from brokers.common.api.ports import MarketDataProvider
from brokers.common.core.enums import ExchangeSegment
from brokers.common.core.models import (
    HistoricalCandle,
    MarketDepth,
    OptionContract,
    Quote,
)
from brokers.dhan.instrument_service import InstrumentService
from brokers.dhan.instruments.mixin import DhanInstrumentMixin
from brokers.dhan.market_data.depth.provider import DhanMarketDepthProvider
from brokers.dhan.market_data.market_data import DhanMarketDataClient
from brokers.dhan.market_data.options import DhanOptionsClient
from brokers.dhan.websocket.order_stream_adapter import DhanOrderStreamProvider


class OrderStreamNotConfigured(RuntimeError):
    """Raised when an order-stream operation is attempted on a provider
    that was constructed without an order-stream provider.

    F14 (M4): previously the adapter masked this failure with
    ``if hasattr(...)`` guards and returned ``False``, leaving operators
    staring at a silent non-subscription.  We now raise so the
    configuration gap is loud.
    """


class DhanMarketDataProvider(MarketDataProvider, DhanInstrumentMixin):
    """Trade_J-style market data adapter over Dhan REST clients."""

    def __init__(
        self,
        market_data_client: DhanMarketDataClient,
        options_client: DhanOptionsClient,
        instrument_service: InstrumentService,
        depth_provider: DhanMarketDepthProvider | None = None,
        order_stream_provider: DhanOrderStreamProvider | None = None,
    ) -> None:
        self._market_data_client = market_data_client
        self._options_client = options_client
        self._instrument_service = instrument_service
        self._depth_provider = depth_provider
        # F14 (M4): the order stream provider is now a required-to-wire
        # constructor argument.  Previously the adapter reached for
        # ``self._order_stream_provider`` only when the attribute
        # *happened* to be present (``if hasattr(...)``), which masked
        # the failure with ``False`` and left order-stream subscriptions
        # silently broken.  Callers that don't have a provider must now
        # pass ``None`` and the adapter raises
        # :class:`OrderStreamNotConfigured` so the failure is loud.
        self._order_stream_provider = order_stream_provider

    @property
    def market_data_client(self) -> DhanMarketDataClient:
        return self._market_data_client

    @property
    def options_client(self) -> DhanOptionsClient:
        return self._options_client

    @property
    def order_stream_provider(self) -> DhanOrderStreamProvider | None:
        return self._order_stream_provider

    def get_quote(
        self,
        security_id: str,
        exchange_segment: ExchangeSegment,
        mode: str = "quote",
    ) -> Quote:
        return self._market_data_client.get_quote(security_id, exchange_segment, mode)

    def get_quote_for_symbol(
        self,
        symbol: str,
        exchange: str,
        mode: str = "quote",
    ) -> Quote:
        resolved = self._resolve_market(symbol, exchange)
        return self.get_quote(resolved.security_id, resolved.exchange_segment, mode)

    def get_historical_daily(
        self,
        security_id: str,
        exchange_segment: ExchangeSegment,
        from_date: date,
        to_date: date,
        instrument: str = "EQUITY",
    ) -> list[HistoricalCandle]:
        return self._market_data_client.get_historical_data(
            security_id,
            exchange_segment,
            from_date,
            to_date,
            instrument=instrument,
        )

    def get_historical_intraday(
        self,
        security_id: str,
        exchange_segment: ExchangeSegment,
        from_date: date,
        to_date: date,
        interval: str | None = None,
        instrument: str = "EQUITY",
    ) -> list[HistoricalCandle]:
        return self._market_data_client.get_historical_data(
            security_id,
            exchange_segment,
            from_date,
            to_date,
            interval=interval,
            instrument=instrument,
        )

    def get_historical_intraday_for_symbol(
        self,
        symbol: str,
        exchange: str,
        from_date: date,
        to_date: date,
        *,
        interval: str | None = None,
        timeframe: str = "1d",
    ) -> list[HistoricalCandle]:
        resolved = self._resolve_market(symbol, exchange)
        if interval is None:
            tf = timeframe.lower()
            if tf in ("1d", "d", "daily"):
                interval = None
            else:
                numeric_part = "".join(filter(str.isdigit, tf))
                interval = numeric_part if numeric_part else "1"
        return self.get_historical_intraday(
            resolved.security_id,
            resolved.exchange_segment,
            from_date,
            to_date,
            interval=interval,
            instrument=resolved.dhan_historical_instrument,
        )

    def get_option_chain(
        self,
        underlying: str,
        exchange_segment: ExchangeSegment,
        expiry: str,
    ) -> list[OptionContract]:
        return self._options_client.get_parsed_option_chain(
            underlying,
            exchange_segment,
            expiry,
        )

    def get_depth(
        self,
        security_id: str,
        exchange_segment: ExchangeSegment,
    ) -> MarketDepth:
        if self._depth_provider:
            return self._depth_provider.get_depth(security_id, exchange_segment)
        return self._market_data_client.get_depth(security_id, exchange_segment)

    def get_depth_for_symbol(self, symbol: str, exchange: str) -> MarketDepth:
        resolved = self._resolve_market(symbol, exchange)
        return self.get_depth(resolved.security_id, resolved.exchange_segment)

    def get_option_expiries(
        self,
        underlying: str,
        exchange_segment: ExchangeSegment,
    ) -> list[str]:
        return self._market_data_client.get_option_expiries(underlying, exchange_segment)

    def get_parsed_option_chain(
        self,
        underlying: str,
        exchange_segment: ExchangeSegment,
        expiry: str,
    ) -> list[OptionContract]:
        return self._options_client.get_parsed_option_chain(
            underlying,
            exchange_segment,
            expiry,
        )

    # ── Order stream integration ─────────────────────────────────────

    def _require_order_stream(self) -> DhanOrderStreamProvider:
        """Return the order stream provider, raising loudly if absent.

        F14 (M4): the previous ``if hasattr(...)`` masks hid the
        configuration gap.  This helper is the single funnel for all
        order-stream methods.
        """
        if self._order_stream_provider is None:
            raise OrderStreamNotConfigured(
                "DhanMarketDataProvider has no order_stream_provider. "
                "Construct it with the order_stream_provider argument "
                "or set it after construction."
            )
        return self._order_stream_provider

    def subscribe_order_stream(self, order_ids: list[str]) -> bool:
        """Subscribe to order stream for specific order IDs.

        Raises :class:`OrderStreamNotConfigured` if no provider is wired.
        """
        return self._require_order_stream().subscribe_order_stream(order_ids)

    def unsubscribe_order_stream(self, order_ids: list[str]) -> bool:
        """Unsubscribe from order stream for specific order IDs."""
        return self._require_order_stream().unsubscribe_order_stream(order_ids)

    def get_order_stream_status(self) -> Dict[str, Any]:
        """Get order stream status."""
        if self._order_stream_provider is None:
            # Status is read-only; returning a sentinel is acceptable
            # (callers want to know "are we connected?"), but the
            # ``connected`` flag is now ``None`` (not ``False``) so a
            # caller can distinguish "intentionally not wired" from
            # "connected and idle".
            return {"connected": None, "subscriptions": 0, "listeners": 0}
        return self._order_stream_provider.get_order_stream_status()

    def add_order_listener(self, listener: Any) -> None:
        """Add an order event listener."""
        self._require_order_stream().add_order_listener(listener)

    def remove_order_listener(self, listener: Any) -> None:
        """Remove an order event listener."""
        self._require_order_stream().remove_order_listener(listener)
