"""DhanConnection — owns auth, transport, rate limiter, sub-adapters."""

from __future__ import annotations

from typing import Any

from plugins.brokers.common.rate_limit import DHAN_RATE_LIMITS, limiter_from_table
from plugins.brokers.common.transport import BaseTransport, HttpTransport
from plugins.brokers.dhan.adapters import (
    DhanInstrumentAdapter,
    DhanMarketDataAdapter,
    DhanOrdersAdapter,
    DhanPortfolioAdapter,
    DhanStreamingAdapter,
)
from plugins.brokers.dhan.auth import DhanTokenManager
from plugins.brokers.dhan.config import DhanConfig
from plugins.brokers.dhan.wire import DhanWire


class DhanConnection:
    def __init__(
        self,
        config: DhanConfig | None = None,
        transport: BaseTransport | None = None,
        token_manager: DhanTokenManager | None = None,
    ) -> None:
        self.config = config or DhanConfig()
        self.wire = DhanWire()
        self._tokens = token_manager or DhanTokenManager(self.config)
        self._limiter = limiter_from_table(DHAN_RATE_LIMITS)
        if transport is not None:
            self.transport = transport
        else:
            self.transport = HttpTransport(
                base_url=self.config.base_url,
                limiter=self._limiter,
                token_provider=self._tokens.current,
                # Dhan uses access-token + client-id headers (not Bearer)
                auth_header="access-token",
                auth_prefix="",
                extra_headers={
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                    "client-id": self.config.client_id,
                },
            )
        self.orders = DhanOrdersAdapter(self.transport, self.wire)
        self.market_data = DhanMarketDataAdapter(self.transport, self.wire)
        self.portfolio = DhanPortfolioAdapter(self.transport, self.wire)
        self.instruments = DhanInstrumentAdapter(self.transport, self.wire)
        self.streaming = DhanStreamingAdapter(
            wire=self.wire,
            ws_url=self.config.ws_url,
            token_provider=self._tokens.current,
            client_id=self.config.client_id,
        )
        self._connected = False
        self._authenticated = False
        self._last_auth_error: Exception | None = None

    def connect(self) -> None:
        self._connected = True

    def authenticate(self) -> bool:
        try:
            token = self._tokens.ensure_token()
            self._authenticated = bool(token)
            extra = getattr(self.transport, "_extra_headers", None)
            if isinstance(extra, dict) and self.config.client_id:
                extra["client-id"] = self.config.client_id
            if not self._authenticated:
                return False
            try:
                self.portfolio.get_funds()
            except Exception as exc:
                msg = str(exc)
                if "401" in msg or "DH-901" in msg or "Invalid_Authentication" in msg:
                    if not self.config.has_totp:
                        raise
                    try:
                        self._tokens.ensure_token(force_refresh=True)
                        self.portfolio.get_funds()
                    except Exception as refresh_exc:
                        # ponytail: if TOTP cooldown blocks refresh, surface original auth error
                        raise refresh_exc from exc
                else:
                    raise
            self._authenticated = True
            return True
        except Exception as exc:
            self._last_auth_error = exc
            self._authenticated = False
            return False

    def disconnect(self) -> None:
        self.streaming.close()
        self._connected = False
        self._authenticated = False

    @property
    def is_connected(self) -> bool:
        return self._connected and self._authenticated

    def load_instruments(self) -> None:
        self.instruments.load_instruments()

    def mass_status(self) -> dict[str, Any]:
        return {
            "orders": self.orders.get_orderbook(),
            "positions": self.portfolio.get_positions(),
            "account": self.portfolio.get_funds(),
        }
