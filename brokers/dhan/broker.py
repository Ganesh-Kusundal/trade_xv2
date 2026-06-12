"""DhanBroker — DhanHQ broker adapter facade.

Wraps the ``dhanhq`` SDK and the new adapter layer behind the
:class:`~brokers.common.core.connection.BrokerConnection` interface.

All REST adapters lives under :mod:`broker.dhan`. The facade:
- Instantiates every adapter.
- Registers capabilities so the ``BrokerRouter`` can discover them.
- Provides the ``_rest_*`` public surface (mirrors Trade_J's REST methods).
- Continues the pre-existing ``dhanhq`` SDK path (connect/disconnect).

Usage::

    broker = DhanBroker(client_id="YOUR_ID", access_token="YOUR_TOKEN")
    broker.connect()
    q = broker.get_market_quote_rest("2885", ExchangeSegment.NSE)
    resp = broker.place_order_rest(OrderRequest(security_id="2885", quantity=1))
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import pandas as pd
from dhanhq import DhanContext, dhanhq  # type: ignore[import-untyped]

import brokers.common.core.domain
import brokers.common.core.mappers

# Backward-compatible attributes: tests and legacy callers monkeypatch
# ``broker.dhan.dhanhq`` to inject a stub SDK.
import brokers.dhan as _dhan_package
from brokers.common.core.auth import AuthManager, TokenSource
from brokers.common.core.broker import Broker
from brokers.common.core.connection import (
    BrokerConnection,
    Capability,
    ConnectionStatus,
)
from brokers.common.core.domain import Side
from brokers.common.core.enums import (
    ExchangeSegment,
    OrderType,
    ProductType,
    TransactionType,
    Validity,
)
from brokers.common.core.instruments import InstrumentRegistry
from brokers.common.core.models import (
    ConditionalAlert,
    ConditionalAlertRequest,
    HistoricalCandle,
    MarketDepth,
    OptionContract,
    Order,
    OrderRequest,
    OrderResponse,
    PnlExitPolicy,
    PnlExitResult,
    Quote,
    SliceOrderRequest,
)
from brokers.common.resilience.errors import RetryableError
from brokers.common.resilience.rate_limiter import (
    MultiBucketRateLimiter,
    RateLimitConfig,
)
from brokers.common.resilience.retry import RetryExecutor
from brokers.dhan.auth.auth import (
    DhanAuthClient,
    DhanTokenManager,
    DhanTokenProvider,
    read_secret_file,
)
from brokers.dhan.auth.revalidator import DhanTokenRevalidator
from brokers.dhan.auth.config import DhanConnectionSettings, DhanSettingsLoader
from brokers.dhan.auth.http import DhanAuthenticatedHttpClient
from brokers.dhan.auth.urls import DhanApiUrlResolver
from brokers.dhan.client import DhanClientHolder, TokenRotationListener
from brokers.dhan.instrument_service import InstrumentNotFoundError, InstrumentService
from brokers.dhan.mapper.instruments import DhanInstrumentResolver
from brokers.dhan.mapper.mapping import (
    decimal_value,
    first_present,
    int_value,
    list_data,
    response_data,
    str_field,
)

_dhan_package.DhanContext = DhanContext
_dhan_package.dhanhq = dhanhq

logger = logging.getLogger(__name__)


class _SdkTokenRotationListener(TokenRotationListener):
    """Rebuild the dhanhq SDK handle when the REST token rotates."""

    def __init__(self, broker: DhanBroker) -> None:
        self._broker = broker

    def on_token_acquired(self, access_token: str, issued_at_ms: int) -> None:
        if not access_token or self._broker._dhan is None:
            return
        ctx = DhanContext(self._broker.client_id, access_token)
        self._broker._dhan = _dhan_package.dhanhq(ctx)  # type: ignore[call-arg]
        self._broker._sync_auth_token(access_token)


class DhanBroker(BrokerConnection, Broker):
    """DhanHQ broker adapter — Trade_J equivalent of ``DhanBrokerConnection``."""

    # ── Factory constructors ─────────────────────────────────────────

    @classmethod
    def from_env(
        cls,
        *,
        env_path: Path | None = None,
        auth_manager: AuthManager | None = None,
    ) -> DhanBroker:
        """Build from ``.env`` / ``.env.local`` settings."""
        settings = DhanSettingsLoader.from_env(env_path=env_path)
        return cls(settings=settings, auth_manager=auth_manager)

    @classmethod
    def from_properties(
        cls,
        path: Path,
        *,
        auth_manager: AuthManager | None = None,
    ) -> DhanBroker:
        """Build from a Trade_J-style ``dhan-local.properties`` file."""
        settings = DhanSettingsLoader.from_properties(path)
        return cls(settings=settings, auth_manager=auth_manager)

    # ── Channel rate limits (matches Trade_J buckets) ────────────────

    _RATE_LIMITS: dict[str, RateLimitConfig] = {
        "orders": RateLimitConfig(rate_per_second=10, capacity=10),
        "quotes": RateLimitConfig(rate_per_second=1, capacity=1),
        "data": RateLimitConfig(rate_per_second=5, capacity=20),
    }

    # ── Initialiser ──────────────────────────────────────────────────

    def __init__(
        self,
        client_id: str = "",
        access_token: str = "",
        auth_manager: AuthManager | None = None,
        auth_mode: str = "STATIC",
        pin_file: Path | None = None,
        totp_secret_file: Path | None = None,
        token_state_file: Path | None = None,
        settings: DhanConnectionSettings | None = None,
        instrument_service: InstrumentService | None = None,
    ) -> None:
        settings = settings or DhanConnectionSettings(
            client_id=client_id,
            access_token=access_token,
            auth_mode=auth_mode,
            pin_file=pin_file,
            totp_secret_file=totp_secret_file,
            token_state_file=token_state_file,
        )

        if not settings.client_id:
            raise ValueError("DhanBroker requires client_id")

        super().__init__(name="dhan", broker_id=settings.client_id)
        self.client_id = settings.client_id
        self.settings = settings
        self._auth_mode = settings.auth_mode

        # AuthManager (static token path)
        if auth_manager:
            self._auth: AuthManager = auth_manager
        else:
            self._auth = AuthManager(
                client_id=settings.client_id,
                token_source=(TokenSource.STATIC if settings.is_static else TokenSource.TOTP),
                on_acquire=lambda: settings.access_token or "",
            )
        if settings.access_token and settings.is_static:
            self._auth._set_token(settings.access_token, TokenSource.STATIC)

        # Token manager (TOTP / WEB_RENEWABLE path)
        self._token_manager: DhanTokenManager | None = None
        self._client_holder: DhanClientHolder | None = None
        if not settings.is_static:
            self._token_manager = DhanTokenManager(
                client_id=settings.client_id,
                access_token=settings.access_token,
                pin=(read_secret_file(settings.pin_file, "pin") if settings.pin_file else None),
                totp_secret=(
                    read_secret_file(settings.totp_secret_file, "totp secret")
                    if settings.totp_secret_file
                    else None
                ),
                auth_mode=settings.auth_mode,
                token_state_file=settings.token_state_file,
                refresh_buffer_minutes=settings.refresh_buffer_minutes,
            )
            self._client_holder = DhanClientHolder(self._token_manager)
            self._client_holder.add_listener(_SdkTokenRotationListener(self))
            self._token_revalidator = DhanTokenRevalidator(
                self._token_manager,
                DhanAuthClient(),
                settings,
            )
        else:
            self._token_revalidator = None

        # SDK client handle
        self._dhan: Any | None = None

        # Resilience (injectable)
        from brokers.dhan.resilience import DhanResilienceConfig

        resilience = DhanResilienceConfig.default()
        self._rate_limiter = resilience.build_rate_limiter()
        self._circuit_breakers = resilience.build_circuit_breakers()
        self._executors: dict[str, RetryExecutor] = resilience.build_executors(
            self._rate_limiter,
            self._circuit_breakers,
        )

        # ── Adapter layer (factory-driven) ──────────────────────────────

        from brokers.dhan.adapters import DhanAdapterFactory

        self.instrument_resolver = DhanInstrumentResolver()
        # M3: own an InstrumentService.  If the caller passes one in we use
        # it verbatim; otherwise we lazily build one whose cache lives under
        # ``settings.instrument_cache_dir`` (or ``.cache/dhan/instruments/``
        # by default).  The service is *not* refreshed here — callers that
        # want a fresh snapshot call ``broker.refresh_instrument_snapshot()``
        # or rely on the first ``load_instrument_catalog`` call to do it.
        cache_dir = settings.instrument_cache_dir or Path("runtime-dev/instruments")
        self.instrument_service: InstrumentService = (
            instrument_service
            if instrument_service is not None
            else InstrumentService(
                cache_dir=cache_dir,
                strict_resolution=settings.instrument_strict_resolution,
            )
        )
        self.instrument_resolver._service = self.instrument_service
        self.url_resolver = DhanApiUrlResolver(settings)
        token_provider: DhanTokenProvider | Callable[[], str] = (
            self._client_holder if self._client_holder is not None else self._access_token
        )
        self.http_client = DhanAuthenticatedHttpClient(token_provider, settings)

        factory = DhanAdapterFactory(
            http_client=self.http_client,
            url_resolver=self.url_resolver,
            executors=self._executors,
            settings=settings,
            token_provider=token_provider,
            instrument_service=self.instrument_service,
        )
        adapters = factory.create_all()

        self.order_client = adapters["order_client"]
        self.market_data_client = adapters["market_data_client"]
        self.portfolio_client = adapters["portfolio_client"]
        self.options_client = adapters["options_client"]
        self.margin_client = adapters["margin_client"]
        self.order_validator = adapters["order_validator"]
        self.idempotency_cache = adapters["idempotency_cache"]
        self.order_command = adapters["order_command"]
        self.order_query = adapters["order_query"]
        self.bracket_order = adapters["bracket_order"]
        self.cover_order = adapters["cover_order"]
        self.gtt_order = adapters["gtt_order"]
        self.slice_order = adapters["slice_order"]
        self.session_risk = adapters["session_risk"]
        self.conditional_alert = adapters["conditional_alert"]
        self.futures = adapters["futures"]
        self.order_stream = adapters["order_stream"]
        self.market_data = adapters["market_data"]
        self.portfolio = adapters["portfolio"]
        self.options = adapters["options"]
        self.margin = adapters["margin"]
        self.market_status = adapters["market_status"]

        # Capability registration after adapter init
        self._register_capability(Capability.MARKET_DATA, self.market_data)
        self._register_capability(Capability.DEPTH, self.market_data)
        self._register_capability(Capability.ORDER_COMMAND, self.order_command)
        self._register_capability(Capability.ORDER_QUERY, self.order_query)
        self._register_capability(Capability.ORDER_STREAM, self.order_stream)
        self._register_capability(Capability.PORTFOLIO, self.portfolio)
        self._register_capability(Capability.OPTIONS_CHAIN, self.options)
        self._register_capability(Capability.HISTORICAL_DATA, self.market_data)
        self._register_capability(Capability.MARGIN, self.margin)
        self._register_capability(Capability.INSTRUMENTS, self.instrument_service)
        self._register_capability(Capability.FUTURES, self.futures)
        self._register_capability(Capability.BRACKET_ORDER, self.bracket_order)
        self._register_capability(Capability.COVER_ORDER, self.cover_order)
        self._register_capability(Capability.GTT_ORDER, self.gtt_order)
        self._register_capability(Capability.SLICE_ORDER, self.slice_order)
        self._register_capability(Capability.SESSION_RISK, self.session_risk)
        self._register_capability(Capability.ALERTS, self.conditional_alert)
        self._register_capability(Capability.IDEMPOTENCY, self.idempotency_cache)
        self._register_capability(Capability.MARKET_STATUS, self.market_status)

    # ── Resilience properties ────────────────────────────────────────

    @property
    def rate_limiter(self) -> MultiBucketRateLimiter:
        return self._rate_limiter

    @property
    def executor(self) -> RetryExecutor:
        """Primary retry executor (order operations)."""
        return self._executors["orders"]

    @property
    def auth(self) -> AuthManager:
        """AuthManager for credential lifecycle."""
        return self._auth

    # ── Internal helpers ──────────────────────────────────────────────

    def _access_token(self) -> str:
        """Current access token — resolves through token manager or AuthManager."""
        if self._client_holder is not None:
            return self._client_holder.ensure_valid_and_get()
        if self._token_manager:
            return self._token_manager.ensure_valid_and_get()
        if not self._auth.ensure_valid():
            raise PermissionError(
                "DhanHQ token expired and could not be refreshed. "
                "Call connect() to re-authenticate."
            )
        if not self._auth.state or not self._auth.state.access_token:
            raise PermissionError("DhanHQ access token is not configured")
        return self._auth.state.access_token

    # ── Instrument + preview helpers ──────────────────────────────────

    def load_instrument_catalog(self, path: Path) -> list[Any]:
        """Load the Dhan master CSV into the canonical :class:`InstrumentService`."""
        self.instrument_service.load_snapshot(path)
        with self.instrument_service._lock:
            catalog = self.instrument_service._indexes.catalog
        return list(catalog._by_security_id.values())

    def refresh_instrument_snapshot(self, force: bool = False):
        """Refresh the broker-owned :class:`InstrumentService` snapshot.

        Returns the new :class:`SnapshotInfo`.  Callers that want
        sub-second read access during a market session should call this
        once at startup, or schedule it daily.
        """
        return self.instrument_service.refresh_snapshot(force=force)

    def resolve_instrument_wire(
        self, symbol: str, exchange: str | ExchangeSegment
    ):
        """Resolve to a :class:`~brokers.dhan.instruments.ResolvedInstrument`."""
        exchange_str = (
            exchange.value if isinstance(exchange, ExchangeSegment) else str(exchange)
        )
        return self.instrument_service.resolve_to_wire(symbol, exchange_str)

    def resolve_instrument(self, symbol: str, exchange: str | ExchangeSegment) -> str:
        """Resolve ``(symbol, exchange)`` to a Dhan security ID."""
        return self.instrument_service.resolve_security_id(symbol, exchange)

    def preview_order(self, order: OrderRequest) -> Any:
        """Validate an order request before placement (advisory-first)."""
        return self.order_validator.validate(order)

    # ── REST order surface ───────────────────────────────────────────

    def place_order_rest(self, order: OrderRequest) -> OrderResponse:
        return self.order_command.place_order(order)

    def modify_order_rest(self, order_id: str, **changes: Any) -> dict[str, Any]:
        return self.order_command.modify_order(order_id, **changes)

    def cancel_order_rest(self, order_id: str) -> bool:
        return self.order_command.cancel_order(order_id)

    def get_order_by_correlation_id_rest(self, correlation_id: str) -> dict[str, Any]:
        result = self.order_query.get_order_by_correlation_id(correlation_id)
        return result or {}

    def get_trade_book_rest(self) -> list[dict[str, Any]]:
        return self.order_query.get_trades()

    def get_trades_for_order_rest(self, order_id: str) -> list[dict[str, Any]]:
        return self.order_query.get_trades_for_order(order_id)

    # ── Order stream surface ───────────────────────────────────────────

    def subscribe_order_stream_rest(self, order_ids: list[str]) -> bool:
        return self.order_stream.subscribe_order_stream(order_ids)

    def unsubscribe_order_stream_rest(self, order_ids: list[str]) -> bool:
        return self.order_stream.unsubscribe_order_stream(order_ids)

    def get_order_stream_status_rest(self) -> dict[str, Any]:
        return self.order_stream.get_order_stream_status()

    def add_order_listener_rest(self, listener: Any) -> None:
        self.order_stream.add_order_listener(listener)

    def remove_order_listener_rest(self, listener: Any) -> None:
        self.order_stream.remove_order_listener(listener)

    # ── Order stream convenience methods ───────────────────────────────

    def subscribe_order_stream(self, order_ids: list[str]) -> bool:
        return self.order_stream.subscribe_order_stream(order_ids)

    def unsubscribe_order_stream(self, order_ids: list[str]) -> bool:
        return self.order_stream.unsubscribe_order_stream(order_ids)

    def get_order_stream_status(self) -> dict[str, Any]:
        return self.order_stream.get_order_stream_status()

    def add_order_listener(self, listener: Any) -> None:
        self.order_stream.add_order_listener(listener)

    def remove_order_listener(self, listener: Any) -> None:
        self.order_stream.remove_order_listener(listener)

    # ── REST market-data surface ─────────────────────────────────────

    def get_market_quote_rest(
        self,
        security_id: str,
        exchange_segment: ExchangeSegment,
        mode: str = "quote",
    ) -> Quote:
        return self.market_data.get_quote(security_id, exchange_segment, mode)

    def get_market_feed_ltp_rest(
        self,
        security_id: str,
        exchange_segment: ExchangeSegment,
    ) -> Quote:
        return self.market_data.get_quote(security_id, exchange_segment, "ltp")

    def get_market_feed_quote_rest(
        self,
        security_id: str,
        exchange_segment: ExchangeSegment,
    ) -> Quote:
        return self.market_data.get_quote(security_id, exchange_segment, "quote")

    def get_market_feed_ohlc_rest(
        self,
        security_id: str,
        exchange_segment: ExchangeSegment,
    ) -> Quote:
        return self.market_data.get_quote(security_id, exchange_segment, "ohlc")

    def get_market_depth_rest(
        self,
        security_id: str,
        exchange_segment: ExchangeSegment,
    ) -> MarketDepth:
        return self.market_data.get_depth(security_id, exchange_segment)

    def get_historical_intraday_rest(
        self,
        security_id: str,
        exchange_segment: ExchangeSegment,
        from_date: date,
        to_date: date,
        interval: str = "1",
        instrument: str = "EQUITY",
    ) -> list[HistoricalCandle]:
        return self.market_data.get_historical_intraday(
            security_id,
            exchange_segment,
            from_date,
            to_date,
            interval=interval,
        )

    # ── REST options surface ─────────────────────────────────────────

    def get_option_expiries_rest(
        self,
        underlying: str,
        exchange_segment: ExchangeSegment,
    ) -> list[str]:
        """Fetch valid expiry dates from Dhan's API.

        Uses the catalog to resolve the correct securityId + segment for the
        underlying (e.g. NIFTY lives on IDX_I, not NSE_FNO).
        Falls back to the seed table if the catalog has not been loaded yet.
        """
        exchange = InstrumentRegistry.canonical_exchange(exchange_segment)
        return self.options.get_expiries_for_symbol(underlying, exchange)

    def get_option_chain_rest(
        self,
        underlying: str,
        exchange_segment: ExchangeSegment,
        expiry: str,
    ) -> list[OptionContract]:
        """Fetch option chain from Dhan's API.

        Resolves the securityId from the catalog before calling the
        options adapter.
        """
        exchange = InstrumentRegistry.canonical_exchange(exchange_segment)
        return self.options.get_option_chain_for_symbol(underlying, exchange, expiry)

    # ── REST margin surface ──────────────────────────────────────────

    def get_margin_rest(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self.margin.calculate_margin(payload)

    def place_super_order_rest(
        self,
        request: OrderRequest,
        target_price: Decimal,
        stop_loss_price: Decimal,
        trailing_jump: Decimal,
    ) -> Order:
        return self.bracket_order.place_super_order(
            request,
            target_price,
            stop_loss_price,
            trailing_jump,
        )

    def get_super_orders_rest(self) -> list[Order]:
        return self.bracket_order.get_super_orders()

    def cancel_super_order_rest(self, order_id: str, leg_name: str) -> bool:
        return self.bracket_order.cancel_super_order(order_id, leg_name)

    def place_forever_order_rest(
        self,
        request: OrderRequest,
        order_flag: str,
        quantity2: int | None = None,
        price2: Decimal | None = None,
        trigger_price2: Decimal | None = None,
    ) -> Order:
        return self.gtt_order.place_forever_order(
            request,
            order_flag,
            quantity2,
            price2,
            trigger_price2,
        )

    def get_forever_orders_rest(self) -> list[Order]:
        return self.gtt_order.get_forever_orders()

    def cancel_forever_order_rest(self, order_id: str) -> bool:
        return self.gtt_order.cancel_forever_order(order_id)

    def place_slice_order_rest(self, request: SliceOrderRequest) -> list[Order]:
        return self.slice_order.place_slice_order(request)

    def enable_pnl_exit_rest(self, policy: PnlExitPolicy) -> PnlExitResult:
        return self.session_risk.enable_pnl_exit(policy)

    def place_alert_rest(self, request: ConditionalAlertRequest) -> str:
        return self.conditional_alert.place_alert(request)

    def get_alert_rest(self, alert_id: str) -> ConditionalAlert:
        return self.conditional_alert.get_alert(alert_id)

    def list_alerts_rest(self) -> list[ConditionalAlert]:
        return self.conditional_alert.list_alerts()

    def delete_alert_rest(self, alert_id: str) -> bool:
        return self.conditional_alert.delete_alert(alert_id)

    def get_futures_rest(self, underlying: str, exchange_segment: ExchangeSegment) -> list[Any]:
        return self.futures.get_contracts(underlying, exchange_segment)

    def get_market_status_rest(self) -> dict[str, Any]:
        return self.market_status.get_market_status()

    # ── Connection lifecycle ─────────────────────────────────────────

    def connect(self) -> bool:
        try:
            if self._token_manager:
                self._token_manager.validate_persisted_token_at_startup()
            token = self._access_token()
            ctx = DhanContext(self.client_id, token)
            self._dhan = _dhan_package.dhanhq(ctx)  # type: ignore[call-arg]
            self._sync_auth_token(token)
            self._set_status(ConnectionStatus.CONNECTED)
            if self._token_revalidator:
                self._token_revalidator.start()
            return True
        except Exception as exc:
            logger.warning("Dhan connect failed: %s", exc)
            self._set_status(ConnectionStatus.DISCONNECTED)
            return False

    def disconnect(self) -> bool:
        if self._token_revalidator:
            self._token_revalidator.stop()
        self._dhan = None
        self._set_status(ConnectionStatus.DISCONNECTED)
        return True

    def reconnect(self) -> bool:
        self.disconnect()
        return self.connect()

    def is_connected(self) -> bool:
        return self.status == ConnectionStatus.CONNECTED

    # ── Private helpers ──────────────────────────────────────────────

    def _sync_auth_token(self, token: str) -> None:
        if not token or self._auth is None:
            return
        source = TokenSource.TOTP if self._token_manager else TokenSource.STATIC
        self._auth._set_token(token, source)

    def _ensure_auth(self) -> bool:
        self._access_token()
        return True

    def _check_response(self, result: Any) -> Any:
        if isinstance(result, dict) and result.get("status") != "success":
            raise RetryableError(result.get("remarks", "API returned failure"))
        return result

    def _execute_with_auth(self, executor: RetryExecutor, fn: Callable[[], Any]) -> Any:
        if self.status != ConnectionStatus.CONNECTED or not self._dhan:
            raise ConnectionError("Not connected to Dhan")
        self._ensure_auth()
        return executor.execute(lambda: self._check_response(fn()))

    # ── SDK-backed operations ────────────────────────────────────────

    # ── SDK-backed operations ────────────────────────────────────────

    def place_order(
        self,
        symbol_or_request: str | OrderRequest,
        exchange: str = "NSE",
        side: Side = Side.BUY,
        quantity: int = 0,
        price: Decimal = Decimal("0"),
        order_type: str = "MARKET",
        product_type: str = "INTRADAY",
        validity: str = "DAY",
        trigger_price: Decimal = Decimal("0"),
        correlation_id: str | None = None,
    ) -> brokers.common.core.domain.OrderResponse:
        if isinstance(symbol_or_request, OrderRequest):
            if symbol_or_request.correlation_id and self.idempotency_cache:
                cached = self.idempotency_cache.get(symbol_or_request.correlation_id)
                if cached is not None:
                    return brokers.common.core.mappers.order_response_to_domain(cached)

            if self.status != ConnectionStatus.CONNECTED or not self._dhan:
                return brokers.common.core.domain.OrderResponse.fail("Not connected to Dhan")
            try:
                result = self._execute_with_auth(
                    self._executors["orders"],
                    lambda: self._dhan.place_order(
                        security_id=symbol_or_request.security_id,
                        exchange_segment=symbol_or_request.exchange_segment.value,
                        transaction_type=symbol_or_request.transaction_type.value,
                        quantity=symbol_or_request.quantity,
                        price=float(symbol_or_request.price) if symbol_or_request.price > 0 else 0,
                        order_type=symbol_or_request.order_type.value,
                        product_type=symbol_or_request.product_type.value,
                        validity=symbol_or_request.validity.value,
                    ),
                )
                response = self._normalize_order_response(result)
                if symbol_or_request.correlation_id and self.idempotency_cache:
                    self.idempotency_cache.put(symbol_or_request.correlation_id, response)
                return brokers.common.core.mappers.order_response_to_domain(response)
            except RetryableError as exc:
                return brokers.common.core.domain.OrderResponse.fail(str(exc))
            except Exception as exc:
                return brokers.common.core.domain.OrderResponse.fail(str(exc))

        segment = self.instrument_service.resolve_exchange_segment(exchange)
        sec_id = self.instrument_service.resolve_security_id(symbol_or_request, exchange)
        req = OrderRequest(
            security_id=sec_id,
            symbol=symbol_or_request,
            exchange=exchange,
            exchange_segment=segment,
            transaction_type=TransactionType.BUY if side == Side.BUY else TransactionType.SELL,
            quantity=quantity,
            price=price,
            trigger_price=trigger_price if trigger_price > 0 else None,
            order_type=OrderType(order_type),
            product_type=ProductType(product_type),
            validity=Validity(validity),
            correlation_id=correlation_id,
        )
        res = self.order_command.place_order(req)
        return brokers.common.core.domain.OrderResponse(
            success=res.success,
            order_id=res.order_id or "",
            message=res.message,
            status=brokers.common.core.domain.OrderStatus.normalize(
                res.order_status.value if res.order_status else "PENDING"
            ),
        )

    def get_order_list(self) -> list[Order]:
        return self.order_query.get_order_list()

    def get_order_by_id(self, order_id: str) -> dict[str, Any] | None:
        try:
            result = self._execute_with_auth(
                self._executors["orders"],
                lambda: self._dhan.get_order_by_id(order_id),  # type: ignore[call-arg]
            )
            items = list_data(result)
            if items:
                return items[0]
            data = response_data(result)
            return data if isinstance(data, dict) else None
        except Exception:
            return None

    def get_order(self, order_id: str) -> brokers.common.core.domain.Order | None:
        raw_order = self.get_order_by_id(order_id)
        if not raw_order:
            return None
        status_str = raw_order.get("orderStatus") or raw_order.get("status") or "PENDING"
        symbol = raw_order.get("tradingSymbol") or raw_order.get("symbol") or ""
        exchange_seg = raw_order.get("exchangeSegment", "NSE_EQ")
        exchange = InstrumentRegistry.canonical_exchange(ExchangeSegment(exchange_seg))
        return brokers.common.core.domain.Order(
            order_id=str(raw_order.get("orderId", "")),
            symbol=symbol,
            exchange=exchange,
            side=Side.BUY if raw_order.get("transactionType") == "BUY" else Side.SELL,
            order_type=brokers.common.core.domain.OrderType(raw_order.get("orderType", "MARKET")),
            quantity=int(raw_order.get("quantity", 0)),
            filled_quantity=int(raw_order.get("filledQty", 0)),
            price=Decimal(str(raw_order.get("price", 0))),
            trigger_price=Decimal(str(raw_order.get("triggerPrice", 0))),
            status=brokers.common.core.domain.OrderStatus.normalize(status_str),
            timestamp=datetime.now(),
            product_type=brokers.common.core.domain.ProductType(
                raw_order.get("productType", "INTRADAY")
            ),
            validity=brokers.common.core.domain.Validity(raw_order.get("validity", "DAY")),
            avg_price=Decimal(str(raw_order.get("averagePrice", 0))),
            reject_reason=raw_order.get("rejectReason", ""),
            correlation_id=raw_order.get("correlationId"),
        )

    def get_orders(self) -> list[brokers.common.core.domain.Order]:
        pydantic_orders = self.get_order_list()
        domain_orders = []
        for o in pydantic_orders:
            exchange = InstrumentRegistry.canonical_exchange(o.exchange_segment)
            domain_orders.append(
                brokers.common.core.domain.Order(
                    order_id=o.order_id,
                    symbol=o.symbol,
                    exchange=exchange,
                    side=Side.BUY if o.transaction_type == TransactionType.BUY else Side.SELL,
                    order_type=brokers.common.core.domain.OrderType(o.order_type.value),
                    quantity=o.quantity,
                    filled_quantity=o.filled_quantity,
                    price=o.price,
                    trigger_price=o.trigger_price if o.trigger_price else Decimal("0"),
                    status=brokers.common.core.domain.OrderStatus.normalize(o.status.value),
                    timestamp=o.order_timestamp,
                    product_type=brokers.common.core.domain.ProductType(o.product_type.value),
                    validity=brokers.common.core.domain.Validity(o.validity.value),
                    avg_price=o.average_price,
                    reject_reason=o.reject_reason or "",
                    correlation_id=o.correlation_id,
                )
            )
        return domain_orders

    def cancel_order(self, order_id: str) -> bool:
        return self.cancel_order_rest(order_id)

    def get_positions(self) -> list[brokers.common.core.domain.Position]:
        try:
            result = self._execute_with_auth(
                self._executors["data"],
                lambda: self._dhan.get_positions(),
            )
            items = list_data(result)
            return [
                brokers.common.core.domain.Position(
                    symbol=str_field(item, "tradingSymbol", "symbol", "symbol_name"),
                    exchange=InstrumentRegistry.canonical_exchange(
                        ExchangeSegment(str_field(item, "exchangeSegment", default="NSE_EQ"))
                    ),
                    quantity=int_value(first_present(item, "netQuantity"), default=0),
                    avg_price=decimal_value(first_present(item, "buyAveragePrice")),
                    ltp=decimal_value(first_present(item, "lastPrice"), default=0),
                    unrealized_pnl=decimal_value(first_present(item, "unrealizedPnl")),
                    realized_pnl=decimal_value(first_present(item, "realizedPnl")),
                    product_type=brokers.common.core.domain.ProductType(
                        str_field(item, "productType", default="INTRADAY")
                    ),
                )
                for item in items
            ]
        except Exception:
            return []

    def get_holdings(self) -> list[brokers.common.core.domain.Holding]:
        try:
            result = self._execute_with_auth(
                self._executors["data"],
                lambda: self._dhan.get_holdings(),
            )
            items = list_data(result)
            return [
                brokers.common.core.domain.Holding(
                    symbol=str_field(item, "tradingSymbol", "symbol", "symbol_name"),
                    exchange=InstrumentRegistry.canonical_exchange(
                        ExchangeSegment(str_field(item, "exchangeSegment", default="NSE_EQ"))
                    ),
                    quantity=int_value(first_present(item, "quantity"), default=0),
                    available_quantity=int_value(
                        first_present(item, "availableQuantity"), default=0
                    ),
                    avg_price=decimal_value(first_present(item, "costPrice")),
                    ltp=decimal_value(first_present(item, "lastPrice"), default=0),
                    pnl=decimal_value(first_present(item, "pnlValue")),
                )
                for item in items
            ]
        except Exception:
            return []

    def get_fund_limits(self) -> brokers.common.core.domain.FundLimits:
        try:
            result = self._execute_with_auth(
                self._executors["data"],
                lambda: self._dhan.get_fund_limits(),
            )
            data = result.get("data", result) if isinstance(result, dict) else result
            if not isinstance(data, dict):
                return brokers.common.core.domain.FundLimits()

            def _d(key: str, *aliases: str) -> Decimal:
                return decimal_value(first_present(data, key, *aliases))

            return brokers.common.core.domain.FundLimits(
                available_balance=_d("availableBalance", "available_balance"),
                used_margin=_d("usedMargin", "used_margin", "utilisedMargin"),
                total_margin=_d("totalMargin", "total_margin", "encashmentAmount"),
            )
        except Exception:
            return brokers.common.core.domain.FundLimits()

    def get_trades(self) -> list[brokers.common.core.domain.Trade]:
        try:
            result = self._execute_with_auth(
                self._executors["orders"],
                lambda: self._dhan.get_trade_book(),
            )
            items = list_data(result)
            return [
                brokers.common.core.domain.Trade(
                    trade_id=str_field(item, "tradeId", "trade_id"),
                    order_id=str_field(item, "orderId", "order_id"),
                    symbol=str_field(item, "tradingSymbol", "symbol", "symbol_name"),
                    exchange=InstrumentRegistry.canonical_exchange(
                        ExchangeSegment(str_field(item, "exchangeSegment", default="NSE_EQ"))
                    ),
                    side=Side.BUY if str_field(item, "transactionType") == "BUY" else Side.SELL,
                    quantity=int_value(first_present(item, "tradedQty", "quantity"), default=0),
                    price=decimal_value(first_present(item, "tradedPrice", "price")),
                    trade_value=decimal_value(first_present(item, "tradedPrice", "price"))
                    * int_value(first_present(item, "tradedQty", "quantity"), default=0),
                    timestamp=datetime.now(),
                    product_type=brokers.common.core.domain.ProductType(
                        str_field(item, "productType", default="INTRADAY")
                    ),
                )
                for item in items
            ]
        except Exception:
            return []

    def get_quote(
        self,
        symbol_or_sec_id: str,
        exchange_or_segment: str | ExchangeSegment,
        *args,
        **kwargs,
    ) -> pd.DataFrame | Quote | None:
        # Detect legacy signature
        is_legacy = isinstance(exchange_or_segment, ExchangeSegment)
        if is_legacy:
            mode = args[0] if args else kwargs.get("mode", "quote")
            try:
                result = self._execute_with_auth(
                    self._executors["quotes"],
                    lambda: self._dhan.quote_data(  # type: ignore[call-arg]
                        {exchange_or_segment.value: [int(symbol_or_sec_id)]},
                    ),
                )
                quote = self._normalize_quote(result, symbol_or_sec_id, exchange_or_segment)
                if quote is not None:
                    return quote
            except (AttributeError, TypeError, ValueError):
                pass
            except Exception:
                return None
            return self.market_data.get_quote(symbol_or_sec_id, exchange_or_segment, mode)

        # New standard signature
        exchange = str(exchange_or_segment).upper()
        quote = self.market_data.get_quote_for_symbol(symbol_or_sec_id, exchange, "quote")
        records = [
            {
                "symbol": symbol_or_sec_id,
                "exchange": exchange,
                "ltp": float(quote.last_price),
                "bid": float(quote.bid) if quote.bid is not None else float("nan"),
                "ask": float(quote.ask) if quote.ask is not None else float("nan"),
                "volume": int(quote.volume),
                "oi": 0,
                "timestamp": quote.timestamp or datetime.now(),
            }
        ]
        df = pd.DataFrame(
            records,
            columns=[
                "symbol",
                "exchange",
                "ltp",
                "bid",
                "ask",
                "volume",
                "oi",
                "timestamp",
            ],
        )
        if not df.empty:
            df["timestamp"] = pd.to_datetime(df["timestamp"])
            df["ltp"] = df["ltp"].astype("Float64")
            df["bid"] = df["bid"].astype("Float64")
            df["ask"] = df["ask"].astype("Float64")
            df["volume"] = df["volume"].astype("Int64")
            df["oi"] = df["oi"].astype("Int64")
        return df

    def get_historical_data(
        self,
        symbol_or_sec_id: str,
        exchange_or_segment: str | ExchangeSegment,
        from_date: date,
        to_date: date,
        timeframe_or_interval: str = "1d",
        *args,
        **kwargs,
    ) -> pd.DataFrame | list[HistoricalCandle]:
        # Detect legacy signature
        is_legacy = (
            isinstance(exchange_or_segment, ExchangeSegment)
            or "instrument" in kwargs
            or (isinstance(timeframe_or_interval, str) and timeframe_or_interval.isdigit())
        )
        if is_legacy:
            interval = timeframe_or_interval
            return self.market_data.get_historical_intraday(
                symbol_or_sec_id,
                exchange_or_segment,
                from_date,
                to_date,
                interval=interval,
            )

        # New standard signature — resolution lives in the market adapter.
        exchange = str(exchange_or_segment).upper()
        candles = self.market_data.get_historical_intraday_for_symbol(
            symbol_or_sec_id,
            exchange,
            from_date,
            to_date,
            timeframe=timeframe_or_interval,
        )

        records = []
        for c in candles:
            records.append(
                {
                    "timestamp": c.timestamp,
                    "open": float(c.open),
                    "high": float(c.high),
                    "low": float(c.low),
                    "close": float(c.close),
                    "volume": int(c.volume),
                    "oi": 0,
                    "symbol": symbol_or_sec_id,
                    "exchange": exchange,
                    "timeframe": timeframe_or_interval,
                }
            )
        df = pd.DataFrame(
            records,
            columns=[
                "timestamp",
                "open",
                "high",
                "low",
                "close",
                "volume",
                "oi",
                "symbol",
                "exchange",
                "timeframe",
            ],
        )
        if not df.empty:
            df["timestamp"] = pd.to_datetime(df["timestamp"])
            df["open"] = df["open"].astype("Float64")
            df["high"] = df["high"].astype("Float64")
            df["low"] = df["low"].astype("Float64")
            df["close"] = df["close"].astype("Float64")
            df["volume"] = df["volume"].astype("Int64")
            df["oi"] = df["oi"].astype("Int64")
        return df

    def get_option_chain(
        self,
        underlying_or_segment: str | ExchangeSegment,
        exchange_or_underlying: str | ExchangeSegment,
        expiry: str,
    ) -> pd.DataFrame | list[OptionContract]:
        # Detect legacy signature — callers that pass ExchangeSegment
        if isinstance(underlying_or_segment, ExchangeSegment):
            # swap: caller passed (ExchangeSegment, str, str)
            return self.get_option_chain_rest(
                exchange_or_underlying,
                underlying_or_segment,
                expiry,
            )
        if isinstance(exchange_or_underlying, ExchangeSegment):
            # caller passed (str, ExchangeSegment, str)
            return self.get_option_chain_rest(
                underlying_or_segment,
                exchange_or_underlying,
                expiry,
            )

        # New standard signature — underlying routing lives in options adapter.
        underlying = underlying_or_segment
        exchange = str(exchange_or_underlying).upper()
        contracts = self.options.get_option_chain_for_symbol(underlying, exchange, expiry)

        records = []
        for c in contracts:
            records.append(
                {
                    "underlying": underlying,
                    "expiry": expiry,
                    "strike": float(c.strike),
                    "option_type": "CE",
                    "ltp": float(c.ce_ltp) if c.ce_ltp is not None else float("nan"),
                    "bid": float(c.ce_bid) if c.ce_bid is not None else float("nan"),
                    "ask": float(c.ce_ask) if c.ce_ask is not None else float("nan"),
                    "volume": int(c.ce_volume) if c.ce_volume is not None else 0,
                    "oi": int(c.ce_oi) if c.ce_oi is not None else 0,
                    "iv": float(c.ce_iv) if c.ce_iv is not None else float("nan"),
                    "delta": float("nan"),
                    "gamma": float("nan"),
                    "theta": float("nan"),
                    "vega": float("nan"),
                    "rho": float("nan"),
                    "timestamp": datetime.now(),
                }
            )
            records.append(
                {
                    "underlying": underlying,
                    "expiry": expiry,
                    "strike": float(c.strike),
                    "option_type": "PE",
                    "ltp": float(c.pe_ltp) if c.pe_ltp is not None else float("nan"),
                    "bid": float(c.pe_bid) if c.pe_bid is not None else float("nan"),
                    "ask": float(c.pe_ask) if c.pe_ask is not None else float("nan"),
                    "volume": int(c.pe_volume) if c.pe_volume is not None else 0,
                    "oi": int(c.pe_oi) if c.pe_oi is not None else 0,
                    "iv": float(c.pe_iv) if c.pe_iv is not None else float("nan"),
                    "delta": float("nan"),
                    "gamma": float("nan"),
                    "theta": float("nan"),
                    "vega": float("nan"),
                    "rho": float("nan"),
                    "timestamp": datetime.now(),
                }
            )

        df = pd.DataFrame(
            records,
            columns=[
                "underlying",
                "expiry",
                "strike",
                "option_type",
                "ltp",
                "bid",
                "ask",
                "volume",
                "oi",
                "iv",
                "delta",
                "gamma",
                "theta",
                "vega",
                "rho",
                "timestamp",
            ],
        )
        if not df.empty:
            df["expiry"] = pd.to_datetime(df["expiry"])
            df["timestamp"] = pd.to_datetime(df["timestamp"])
            df["strike"] = df["strike"].astype("Float64")
            df["ltp"] = df["ltp"].astype("Float64")
            df["bid"] = df["bid"].astype("Float64")
            df["ask"] = df["ask"].astype("Float64")
            df["volume"] = df["volume"].astype("Int64")
            df["oi"] = df["oi"].astype("Int64")
            df["iv"] = df["iv"].astype("Float64")
            for col in ("delta", "gamma", "theta", "vega", "rho"):
                df[col] = df[col].astype("Float64")
        return df

    def get_market_depth(
        self,
        symbol: str,
        exchange: str,
    ) -> pd.DataFrame:
        depth = self.market_data.get_depth_for_symbol(symbol, exchange)
        record = {
            "symbol": symbol,
            "timestamp": depth.timestamp or datetime.now(),
        }
        for i in range(1, 21):
            if i <= len(depth.bids):
                b = depth.bids[i - 1]
                record[f"bid_price_{i}"] = float(b.price)
                record[f"bid_qty_{i}"] = int(b.quantity)
            else:
                record[f"bid_price_{i}"] = 0.0
                record[f"bid_qty_{i}"] = 0
            if i <= len(depth.asks):
                a = depth.asks[i - 1]
                record[f"ask_price_{i}"] = float(a.price)
                record[f"ask_qty_{i}"] = int(a.quantity)
            else:
                record[f"ask_price_{i}"] = 0.0
                record[f"ask_qty_{i}"] = 0
        df = pd.DataFrame([record])
        df["timestamp"] = pd.to_datetime(df["timestamp"])
        for i in range(1, 21):
            df[f"bid_price_{i}"] = df[f"bid_price_{i}"].astype("Float64")
            df[f"bid_qty_{i}"] = df[f"bid_qty_{i}"].astype("Int64")
            df[f"ask_price_{i}"] = df[f"ask_price_{i}"].astype("Float64")
            df[f"ask_qty_{i}"] = df[f"ask_qty_{i}"].astype("Int64")
        return df

    # ── Normalization helpers ─────────────────────────────────────────

    def _normalize_order_response(self, result: Any) -> OrderResponse:
        return self._normalize_order(result)

    def _normalize_order(self, result: Any) -> OrderResponse:
        data = result.get("data", result) if isinstance(result, dict) else result
        order_id = str_field(data, "orderId")
        if not order_id:
            return OrderResponse.create_failure(
                str_field(result, "remarks", default="Order failed")
                if isinstance(result, dict)
                else "Order failed"
            )
        return OrderResponse.create_success(
            order_id=order_id,
            message=str_field(data, "status", default="OPEN") if isinstance(data, dict) else "OPEN",
        )

    def _normalize_orders(self, result: Any) -> list[Order]:
        if isinstance(result, dict) and result.get("status") == "success":
            return [
                Order(
                    order_id=str_field(item, "orderId"),
                    symbol=str_field(item, "tradingSymbol", "symbol"),
                )
                for item in list_data(result)
            ]
        return []

    def _normalize_quote(
        self,
        response: Any,
        security_id: str,
        exchange_segment: ExchangeSegment,
    ) -> Quote | None:
        if not isinstance(response, dict):
            return None
        data = response.get("data", response)
        if not isinstance(data, dict):
            return None
        last_price_raw = data.get("last_price") or data.get("lastTradedPrice") or data.get("ltp")
        return Quote(
            exchange_segment=exchange_segment,
            last_price=Decimal(last_price_raw) if last_price_raw else Decimal("0"),
            open=Decimal(str(data["open"])) if "open" in data else Decimal("0"),
            high=Decimal(str(data["high"])) if "high" in data else Decimal("0"),
            low=Decimal(str(data["low"])) if "low" in data else Decimal("0"),
            close=Decimal(str(data["close"])) if "close" in data else Decimal("0"),
            volume=int(data.get("volume") or data.get("trade_volume") or 0),
        )
