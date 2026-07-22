"""Upstox wire adapter — sanctioned transport boundary over UpstoxBroker."""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any

import pandas as pd

from domain.capabilities.broker_capabilities import BrokerCapabilities
from brokers.common.capabilities_validator import enforce_gateway_capabilities
from brokers.common.wire_base import BaseWireAdapter
from brokers.providers.upstox.adapters import (
    HistoricalAdapter,
    PortfolioAdapter,
    StreamManagerAdapter,
)
from brokers.providers.upstox.adapters.market_data_gateway import MarketDataGateway
from brokers.providers.upstox.adapters.order_gateway import OrderGateway
from brokers.providers.upstox.adapters.portfolio_gateway import PortfolioGateway
from brokers.providers.upstox.adapters.streaming_gateway import StreamingGateway
from brokers.providers.upstox.broker import UpstoxBroker
from brokers.providers.upstox.capabilities import upstox_capabilities
from brokers.providers.upstox.extras import UpstoxExtendedCapabilities
from brokers.providers.upstox.market_data.market_data_adapter import (
    UpstoxMarketDataAdapter as MarketDataAdapter,
)
from domain.entities import (
    Balance,
    FutureChain,
    Holding,
    MarketDepth,
    OptionChain,
    Order,
    OrderResponse,
    Position,
    Quote,
    Trade,
)
from domain.market_enums import ExchangeSegment
from domain.constants import DEFAULT_DERIVATIVES_EXCHANGE, DEFAULT_EXCHANGE
from domain.ports.broker_adapter import BrokerAdapter
from domain.orders.requests import OrderRequest
from infrastructure.batch_mixin import BatchFetchMixin

logger = logging.getLogger(__name__)


class UpstoxWireAdapter(BatchFetchMixin, BaseWireAdapter, BrokerAdapter):
    """Unified Upstox broker API — composes gateway adapters over UpstoxBroker."""

    broker_id = "upstox"

    @property
    def broker(self) -> UpstoxBroker:
        return self._broker

    def _transport_connected(self) -> bool:
        """Authenticated + transport alive.

        Upstox historically returned ``status == CONNECTED`` even when the token
        was expired. We now also require a current (non-expired) token so the
        verdict matches reality.
        """
        from domain.capabilities import ConnectionStatus

        if self._broker.status != ConnectionStatus.CONNECTED:
            return False
        tm = getattr(self._broker, "token_manager", None)
        if tm is None:
            return True
        token = None
        try:
            token = tm.current_token()
        except Exception:
            token = None
        return bool((token or "").strip())

    def authenticate(self) -> bool:
        """BrokerAdapter lifecycle hook — delegates to the broker's connect."""
        return bool(self._broker.connect())

    def __init__(self, broker: UpstoxBroker):
        self._broker = broker

        self._market_data = MarketDataAdapter(
            broker.market_data_v2, broker.market_data_v3, broker.historical_v2
        )
        self._historical = HistoricalAdapter(broker)
        self._stream_manager = StreamManagerAdapter(broker, broker.instrument_resolver)
        self._portfolio = PortfolioAdapter(broker)
        self._order_command = broker.order_command

        self._data_gw = MarketDataGateway(broker, self._market_data, self._historical)
        self._order_gw = OrderGateway(broker, self._order_command, self._portfolio)
        self._stream_gw = StreamingGateway(
            broker,
            self._stream_manager,
            self._data_gw._resolve_instrument_key,
        )
        self._portfolio_gw = PortfolioGateway(self._portfolio)

        from domain.options.gateway_facade import GatewayOptionsFacade

        options_attr = getattr(self._broker, "options", None)
        if options_attr is not None:
            self.options = GatewayOptionsFacade(
                options_attr, exchange_normalize=_upstox_normalize_exchange
            )

        enforce_gateway_capabilities(self)

    @property
    def _stream_registry(self) -> dict:
        return self._stream_manager._stream_registry

    @property
    def _stream_lock(self):
        return self._stream_manager._stream_lock

    def ltp(self, symbol: str, exchange: str = DEFAULT_EXCHANGE) -> Decimal:
        return self._data_gw.ltp(symbol, exchange)

    def quote(self, symbol: str, exchange: str = DEFAULT_EXCHANGE) -> Quote:
        return self._data_gw.quote(symbol, exchange)

    def depth(self, symbol: str, exchange: str = DEFAULT_EXCHANGE) -> MarketDepth:
        return self._data_gw.depth(symbol, exchange)

    def ltp_batch(self, symbols: list[str], exchange: str = DEFAULT_EXCHANGE) -> dict[str, Decimal]:
        return self._data_gw.ltp_batch(symbols, exchange)

    def quote_batch(self, symbols: list[str], exchange: str = DEFAULT_EXCHANGE) -> dict[str, Quote]:
        return self._data_gw.quote_batch(symbols, exchange)

    def history(
        self,
        symbol: str,
        exchange: str = DEFAULT_EXCHANGE,
        timeframe: str = "1D",
        lookback_days: int = 90,
        from_date: str | None = None,
        to_date: str | None = None,
    ) -> pd.DataFrame:
        return self._data_gw.history(symbol, exchange, timeframe, lookback_days, from_date, to_date)

    def get_expired_option_expiries(self, instrument_key: str) -> list[str]:
        return self.extended.get_expired_option_expiries(instrument_key)

    def get_expired_historical_candles(
        self,
        expired_instrument_key: str,
        interval: str,
        from_date,
        to_date,
    ) -> dict[str, Any]:
        return self.extended.get_expired_historical_candles(
            expired_instrument_key, interval, from_date, to_date
        )

    def option_chain(
        self,
        underlying: str,
        exchange: str = DEFAULT_DERIVATIVES_EXCHANGE,
        expiry: str | None = None,
    ) -> OptionChain:
        return self._data_gw.option_chain(underlying, exchange, expiry)

    def future_chain(
        self, underlying: str, exchange: str = DEFAULT_DERIVATIVES_EXCHANGE
    ) -> FutureChain:
        return self._data_gw.future_chain(underlying, exchange)

    def search(self, query: str) -> list[dict]:
        return self._data_gw.search(query)

    def load_instruments(self, source: str | None = None, use_cache: bool = True) -> None:
        self._broker.instruments.load(source=source)

    def close(self) -> None:
        self._data_gw.close()

    def describe(self) -> dict:
        return self._data_gw.describe()

    def place_order(self, request: OrderRequest) -> OrderResponse:
        from brokers.services._session import check_live_actionable

        check_live_actionable(self.broker_id)
        return self._order_gw.place_order(request)

    def cancel_order(self, order_id: str) -> OrderResponse:
        return self._order_gw.cancel_order(order_id)

    def get_order(self, order_id: str) -> Order | None:
        return self._order_gw.get_order(order_id)

    def modify_order(self, order_id: str, **changes: Any) -> OrderResponse:
        return self._order_gw.modify_order(order_id, **changes)

    def get_orderbook(self) -> list[Order]:
        return self._order_gw.get_orderbook()

    def get_trade_book(self) -> list[Trade]:
        return self._order_gw.get_trade_book()

    def trades(self) -> list[Trade]:
        return super().trades()

    def stream(
        self,
        symbol: str,
        exchange: str = DEFAULT_EXCHANGE,
        mode: str = "LTP",
        on_tick: Any | None = None,
    ) -> Any:
        return self._stream_gw.stream(symbol, exchange, mode, on_tick)

    def unstream(
        self, symbol: str, exchange: str = DEFAULT_EXCHANGE, on_tick: Any | None = None
    ) -> None:
        self._stream_gw.unstream(symbol, exchange, on_tick)

    def stream_order(self, on_order: Any | None = None) -> Any:
        return self._stream_gw.stream_order(on_order)

    def stream_depth(
        self,
        symbol: str,
        exchange: str = DEFAULT_EXCHANGE,
        *,
        levels: int = 5,
        on_depth: Any | None = None,
        depth_type: str | None = None,  # deprecated — use levels
    ) -> Any:
        return self._stream_gw.stream_depth(symbol, exchange, levels=levels, on_depth=on_depth, depth_type=depth_type)

    def funds(self) -> Balance:
        return self._portfolio_gw.funds()

    def positions(self) -> list[Position]:
        return self._portfolio_gw.positions()

    def holdings(self) -> list[Holding]:
        return self._portfolio_gw.holdings()

    @property
    def extended(self) -> Any:
        if not hasattr(self, "_extended_cache"):
            self._extended_cache = UpstoxExtendedCapabilities(self._broker)
        return self._extended_cache

    @property
    def news(self) -> Any:
        return self._broker.news

    def capabilities(self) -> BrokerCapabilities:
        return upstox_capabilities()

    def list_capabilities(self):
        """BrokerAdapter-compatible capability descriptor (session kernel)."""
        from domain.capabilities.broker_capabilities import CapabilityDescriptor

        return CapabilityDescriptor.build(self.capabilities(), frozenset())

    @staticmethod
    def _canonical_symbol_for_defn(defn: Any, fallback_key: str = "") -> str:
        from brokers.providers.upstox.adapters.tick_translator import TickTranslatorAdapter

        return TickTranslatorAdapter._canonical_symbol_for_defn(defn, fallback_key)

    def _resolve_instrument_key(self, symbol: str, exchange: str) -> str:
        return self._data_gw._resolve_instrument_key(symbol, exchange)

    def _resolve_exchange_segment(self, exchange: str, symbol: str = "") -> ExchangeSegment:
        return self._order_gw._resolve_exchange_segment(exchange, symbol)

    def _resolve_keys(self, symbols: list[str], exchange: str) -> tuple[dict[str, str], list[str]]:
        return self._data_gw._resolve_keys(symbols, exchange)

    def _map_batch_to_symbols(
        self, symbols: list[str], key_to_sym: dict[str, str], raw: dict[str, Any], *, default: Any
    ) -> dict[str, Any]:
        return self._data_gw._map_batch_to_symbols(symbols, key_to_sym, raw, default=default)

    def _translate_tick_to_quote(self, raw: dict[str, Any]) -> Quote:
        return self._stream_gw._translate_tick_to_quote(raw)

    def get_connection_status(self) -> dict[str, bool]:
        return self._stream_gw.get_connection_status()

    def get_circuit_breaker_states(self) -> dict[str, int]:
        ctx = getattr(self._broker, "context", None)
        if ctx is None:
            return {}
        return ctx.http_client.circuit_breaker_states()

    def get_token_refresh_metrics(self) -> dict[str, int]:
        ctx = getattr(self._broker, "context", None)
        if ctx is None:
            return {"refresh_count": 0, "error_count": 0}
        tm = ctx.token_manager
        return {
            "refresh_count": int(getattr(tm, "refresh_count", 0) or 0),
            "error_count": int(getattr(tm, "error_count", 0) or 0),
        }

    def get_rate_limiter_metrics(self) -> dict[str, int]:
        ctx = getattr(self._broker, "context", None)
        if ctx is None:
            return {"tokens_available": 0, "requests_throttled": 0}
        rl = ctx.rate_limiter
        total = sum(int(rl.get_bucket(c).available_tokens) for c in rl.categories())
        return {"tokens_available": total, "requests_throttled": 0}


def _upstox_normalize_exchange(symbol: str, exchange: str) -> str:
    return exchange


def create_wire_adapter(broker: UpstoxBroker | UpstoxWireAdapter) -> UpstoxWireAdapter:
    if isinstance(broker, UpstoxWireAdapter):
        return broker
    return UpstoxWireAdapter(broker)


__all__ = [
    "UpstoxWireAdapter",
    "create_wire_adapter",
]
