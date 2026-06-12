"""DhanHQ broker provider for the canonical Python SPI."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from brokers.common.api.spi import (
    BrokerDescriptor,
    BrokerProvider,
    BrokerSource,
    CapabilityMetadata,
    descriptor_from_capabilities,
)
from brokers.dhan.auth.config import DhanConnectionSettings
from brokers.dhan.broker import DhanBroker


class DhanBrokerProvider(BrokerProvider):
    """Provider factory for creating ``DhanBroker`` instances."""

    descriptor: BrokerDescriptor = descriptor_from_capabilities(
        source=BrokerSource.DHAN,
        name="DhanHQ",
        capabilities=(
            (
                "MarketDataProvider",
                CapabilityMetadata("LTP, quotes, OHLC, historical candles", True, "market"),
            ),
            (
                "OptionsProvider",
                CapabilityMetadata("Option chain and expiries", True, "market"),
            ),
            (
                "OrderCommand",
                CapabilityMetadata("Place, modify, cancel orders", True, "orders"),
            ),
            (
                "OrderQuery",
                CapabilityMetadata("Order and trade queries", True, "orders"),
            ),
            (
                "PortfolioProvider",
                CapabilityMetadata("Positions, holdings, funds, ledger", True, "portfolio"),
            ),
            ("MarginProvider", CapabilityMetadata("Margin calculator", True, "risk")),
            (
                "InstrumentResolver",
                CapabilityMetadata("Instrument master resolver", True, "services"),
            ),
            (
                "HistoricalDataProvider",
                CapabilityMetadata("Daily and intraday candles", True, "market"),
            ),
            (
                "WebSocketMultiplexer",
                CapabilityMetadata("Not implemented", False, "streaming"),
            ),
            (
                "FuturesProvider",
                CapabilityMetadata("Futures contract lookup", True, "market"),
            ),
            (
                "BracketOrderProvider",
                CapabilityMetadata("Super/bracket orders", True, "orders"),
            ),
            (
                "CoverOrderProvider",
                CapabilityMetadata("Cover orders require dedicated Dhan endpoint", False, "orders"),
            ),
            ("GttOrderProvider", CapabilityMetadata("GTT/forever orders", True, "orders")),
            ("SliceOrderCommand", CapabilityMetadata("Order slicing", True, "orders")),
            (
                "SessionRiskProvider",
                CapabilityMetadata("PnL-exit automation", True, "risk"),
            ),
            (
                "ConditionalAlertProvider",
                CapabilityMetadata("Conditional alerts", True, "services"),
            ),
            (
                "IdempotencyCachePort",
                CapabilityMetadata("In-memory idempotency cache", True, "safety"),
            ),
            ("NewsProvider", CapabilityMetadata("Not supported", False, "services")),
        ),
        metadata={
            "environment": "LIVE/SANDBOX",
            "authModes": "STATIC/TOTP_GENERATED/WEB_RENEWABLE",
        },
        supported_segments=(
            "NSE_EQ",
            "BSE_EQ",
            "NSE_FNO",
            "BSE_FNO",
            "MCX_COMM",
            "NSE_CURRENCY",
            "BSE_CURRENCY",
            "IDX_I",
        ),
        rate_limit_info="Orders:10rps Data:5rps Quotes:1rps OptionChain:1rps",
    )

    def create(self, **kwargs: Any) -> DhanBroker:
        settings = kwargs.pop("settings", None)
        if settings is None:
            settings = self._settings_from_kwargs(kwargs)
        return DhanBroker(settings=settings)

    @staticmethod
    def _first(*values: Any) -> Any:
        """Return the first truthy value from ``values``.

        Used to accept both ``snake_case`` and ``camelCase`` kwarg names
        without repeating the ``get(a) or get(b)`` pattern throughout the
        method.
        """
        for value in values:
            if value:
                return value
        return values[-1] if values else None

    def _settings_from_kwargs(self, kwargs: Mapping[str, Any]) -> DhanConnectionSettings:
        token_state_file = self._first(kwargs.get("token_state_file"), kwargs.get("tokenStateFile"))
        pin_file = self._first(kwargs.get("pin_file"), kwargs.get("pinFile"))
        totp_secret_file = self._first(kwargs.get("totp_secret_file"), kwargs.get("totpSecretFile"))
        return DhanConnectionSettings(
            client_id=str(
                self._first(
                    kwargs.get("client_id"),
                    kwargs.get("clientId"),
                    kwargs.get("client_id", ""),
                )
            ),
            access_token=str(
                self._first(kwargs.get("access_token"), kwargs.get("accessToken")) or ""
            ),
            auth_mode=str(self._first(kwargs.get("auth_mode"), kwargs.get("authMode")) or "STATIC"),
            environment=str(self._first(kwargs.get("environment")) or "LIVE"),
            rest_base_url=str(
                self._first(kwargs.get("rest_base_url"), kwargs.get("restBaseUrl")) or ""
            ),
            pin=kwargs.get("pin"),
            totp_secret=self._first(kwargs.get("totp_secret"), kwargs.get("totpSecret")),
            pin_file=Path(pin_file) if pin_file else None,
            totp_secret_file=(Path(totp_secret_file) if totp_secret_file else None),
            token_state_file=(Path(token_state_file) if token_state_file else None),
            refresh_buffer_minutes=int(
                self._first(
                    kwargs.get("refresh_buffer_minutes"),
                    kwargs.get("refreshBufferMinutes"),
                    10,
                )
            ),
        )
