"""UpstoxBrokerGateway — thin sync facade delegating to specialized adapters.

Composes 4 gateway adapters:
- MarketDataGateway: LTP, quote, depth, history, chains, search, lifecycle
- OrderGateway: place, cancel, modify, orderbook, trade book
- StreamingGateway: WebSocket streams, tick parsing, depth streaming
- PortfolioGateway: funds, positions, holdings

Thread Safety:
    All adapters are thread-safe. The facade itself is stateless except for
    delegating to StreamManagerAdapter which manages subscription state.
"""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any

import pandas as pd

from infrastructure.batch_mixin import BatchFetchMixin
from brokers.common.broker_capabilities import BrokerCapabilities
from brokers.upstox.adapters import (
    HistoricalAdapter,
    PortfolioAdapter,
    StreamManagerAdapter,
)
from brokers.upstox.adapters.market_data_gateway import MarketDataGateway
from brokers.upstox.adapters.order_gateway import OrderGateway
from brokers.upstox.adapters.portfolio_gateway import PortfolioGateway
from brokers.upstox.adapters.streaming_gateway import StreamingGateway
from brokers.upstox.broker import UpstoxBroker
from brokers.common.capabilities_validator import enforce_gateway_capabilities
from brokers.upstox.capabilities import upstox_capabilities
from brokers.upstox.extended import UpstoxExtendedCapabilities
from brokers.upstox.market_data.market_data_adapter import (
    UpstoxMarketDataAdapter as MarketDataAdapter,
)
from domain import (
    Balance,
    ExchangeSegment,
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

logger = logging.getLogger(__name__)


class UpstoxBrokerGateway(BatchFetchMixin):
    """Unified Upstox broker API. All calls delegate to gateway adapters."""

    def __init__(self, broker: UpstoxBroker):
        """Initialize gateway with broker facade and create adapters."""
        self._broker = broker

        self._market_data = MarketDataAdapter(
            broker.market_data_v2, broker.market_data_v3, broker.historical_v2
        )
        self._historical = HistoricalAdapter(broker)
        self._stream_manager = StreamManagerAdapter(broker, broker.instrument_resolver)
        self._portfolio = PortfolioAdapter(broker)
        self._order_command = broker.order_command

        # Compose gateway adapters
        self._data_gw = MarketDataGateway(broker, self._market_data, self._historical)
        self._order_gw = OrderGateway(broker, self._order_command, self._portfolio)
        self._stream_gw = StreamingGateway(
            broker, self._stream_manager, self._data_gw._resolve_instrument_key,
        )
        self._portfolio_gw = PortfolioGateway(self._portfolio)

        # Broker-agnostic options facade for CLI / tests.
        from domain.options.gateway_facade import GatewayOptionsFacade

        options_attr = getattr(self._broker, "options", None)
        if options_attr is not None:
            self.options = GatewayOptionsFacade(
                options_attr, exchange_normalize=_upstox_normalize_exchange
            )

        enforce_gateway_capabilities(self)

    # ── Backward compatibility properties ────────────────────────────────

    @property
    def _stream_registry(self) -> dict:
        return self._stream_manager._stream_registry

    @property
    def _stream_lock(self):
        return self._stream_manager._stream_lock

    # ── Market Data ──────────────────────────────────────────────────────

    def ltp(self, symbol: str, exchange: str = "NSE") -> Decimal:
        return self._data_gw.ltp(symbol, exchange)

    def quote(self, symbol: str, exchange: str = "NSE") -> Quote:
        return self._data_gw.quote(symbol, exchange)

    def depth(self, symbol: str, exchange: str = "NSE") -> MarketDepth:
        return self._data_gw.depth(symbol, exchange)

    def ltp_batch(self, symbols: list[str], exchange: str = "NSE") -> dict[str, Decimal]:
        return self._data_gw.ltp_batch(symbols, exchange)

    def quote_batch(self, symbols: list[str], exchange: str = "NSE") -> dict[str, Quote]:
        return self._data_gw.quote_batch(symbols, exchange)

    def history(
        self, symbol: str, exchange: str = "NSE", timeframe: str = "1D",
        lookback_days: int = 90, from_date: str | None = None,
        to_date: str | None = None,
    ) -> pd.DataFrame:
        return self._data_gw.history(symbol, exchange, timeframe, lookback_days, from_date, to_date)

    def option_chain(self, underlying: str, exchange: str = "NFO", expiry: str | None = None) -> OptionChain:
        return self._data_gw.option_chain(underlying, exchange, expiry)

    def future_chain(self, underlying: str, exchange: str = "NFO") -> FutureChain:
        return self._data_gw.future_chain(underlying, exchange)

    def search(self, query: str) -> list[dict]:
        return self._data_gw.search(query)

    def load_instruments(self, source: str | None = None) -> None:
        """Load instruments via the broker-internal instrument service."""
        self._broker.instruments.load(source=source)

    def close(self) -> None:
        self._data_gw.close()

    def describe(self) -> dict:
        return self._data_gw.describe()

    # ── Order Operations ────────────────────────────────────────────────

    def place_order(
        self, symbol: str, exchange: str = "NSE", side: str = "BUY",
        quantity: int = 1, price: Decimal = Decimal("0"),
        order_type: str = "MARKET", product_type: str = "INTRADAY",
        validity: str = "DAY", trigger_price: Decimal = Decimal("0"),
        correlation_id: str | None = None, is_amo: bool = False,
    ) -> OrderResponse:
        return self._order_gw.place_order(
            symbol, exchange, side, quantity, price, order_type,
            product_type, validity, trigger_price, correlation_id, is_amo,
        )

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

    # ── Streaming ───────────────────────────────────────────────────────

    def stream(self, symbol: str, exchange: str = "NSE", mode: str = "LTP", on_tick: Any | None = None) -> Any:
        return self._stream_gw.stream(symbol, exchange, mode, on_tick)

    def unstream(self, symbol: str, exchange: str = "NSE", on_tick: Any | None = None) -> None:
        self._stream_gw.unstream(symbol, exchange, on_tick)

    def stream_order(self, on_order: Any | None = None) -> Any:
        return self._stream_gw.stream_order(on_order)

    def stream_depth(self, symbol: str, exchange: str = "NSE", depth_type: str = "DEPTH_5", on_depth: Any | None = None) -> Any:
        return self._stream_gw.stream_depth(symbol, exchange, depth_type, on_depth)

    # ── Portfolio ───────────────────────────────────────────────────────

    def funds(self) -> Balance:
        return self._portfolio_gw.funds()

    def positions(self) -> list[Position]:
        return self._portfolio_gw.positions()

    def holdings(self) -> list[Holding]:
        return self._portfolio_gw.holdings()

    def trades(self) -> list[Trade]:
        return self.get_trade_book()

    # ── Extended Capabilities ───────────────────────────────────────────

    @property
    def extended(self) -> Any:
        return UpstoxExtendedCapabilities(self._broker)

    @property
    def news(self) -> Any:
        return self._broker.news

    # ── Broker metadata ─────────────────────────────────────────────────

    def capabilities(self) -> BrokerCapabilities:
        return upstox_capabilities()

    @staticmethod
    def _canonical_symbol_for_defn(defn: Any, fallback_key: str = "") -> str:
        from brokers.upstox.adapters.tick_translator import TickTranslatorAdapter
        return TickTranslatorAdapter._canonical_symbol_for_defn(defn, fallback_key)

    # ── Internal helpers (backward compat for tests) ────────────────────

    def _resolve_instrument_key(self, symbol: str, exchange: str) -> str:
        return self._data_gw._resolve_instrument_key(symbol, exchange)

    def _resolve_exchange_segment(self, exchange: str, symbol: str = "") -> ExchangeSegment:
        return self._order_gw._resolve_exchange_segment(exchange, symbol)

    def _resolve_keys(self, symbols: list[str], exchange: str) -> tuple[dict[str, str], list[str]]:
        return self._data_gw._resolve_keys(symbols, exchange)

    def _map_batch_to_symbols(self, symbols: list[str], key_to_sym: dict[str, str], raw: dict[str, Any], *, default: Any) -> dict[str, Any]:
        return self._data_gw._map_batch_to_symbols(symbols, key_to_sym, raw, default=default)

    def _translate_tick_to_quote(self, raw: dict[str, Any]) -> Quote | dict[str, Any]:
        return self._stream_gw._translate_tick_to_quote(raw)

    # ── ObservabilityProvider ───────────────────────────────────────────

    def get_connection_status(self) -> dict[str, bool]:
        return self._stream_gw.get_connection_status()

    def get_circuit_breaker_states(self) -> dict[str, int]:
        from infrastructure.resilience.circuit_breaker import CircuitState
        http = self._broker.context.http_client
        mapping = {"read": http._read_circuit_breaker, "write": http._write_circuit_breaker, "admin": http._admin_circuit_breaker}
        return {name: cb.state.value if cb is not None else CircuitState.CLOSED.value for name, cb in mapping.items()}

    def get_token_refresh_metrics(self) -> dict[str, int]:
        tm = self._broker.context.token_manager
        return {"refresh_count": getattr(tm, "refresh_count", 0), "error_count": getattr(tm, "error_count", 0)}

    def get_rate_limiter_metrics(self) -> dict[str, int]:
        rl = self._broker.context.rate_limiter
        total = sum(int(rl.get_bucket(c).available_tokens) for c in rl.categories())
        return {"tokens_available": total, "requests_throttled": 0}


def _upstox_normalize_exchange(symbol: str, exchange: str) -> str:
    return exchange
