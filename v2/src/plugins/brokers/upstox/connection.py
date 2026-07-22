"""UpstoxConnection — auth + transport + sub-adapters."""

from __future__ import annotations

from typing import Any

from plugins.brokers.common.rate_limit import UPSTOX_RATE_LIMITS, limiter_from_table
from plugins.brokers.common.transport import BaseTransport, HttpTransport
from plugins.brokers.upstox.adapters import (
    UpstoxInstrumentAdapter,
    UpstoxMarketDataAdapter,
    UpstoxOrdersAdapter,
    UpstoxPortfolioAdapter,
    UpstoxStreamingAdapter,
)
from plugins.brokers.upstox.auth import UpstoxTokenManager
from plugins.brokers.upstox.config import UpstoxConfig
from plugins.brokers.upstox.wire import UpstoxWire


class UpstoxConnection:
    def __init__(
        self,
        config: UpstoxConfig | None = None,
        transport: BaseTransport | None = None,
        token_manager: UpstoxTokenManager | None = None,
    ) -> None:
        self.config = config or UpstoxConfig()
        self.wire = UpstoxWire()
        self._tokens = token_manager or UpstoxTokenManager(self.config)
        self._limiter = limiter_from_table(UPSTOX_RATE_LIMITS)
        if transport is not None:
            self.transport = transport
        else:
            self.transport = HttpTransport(
                base_url=self.config.base_url,
                limiter=self._limiter,
                token_provider=self._tokens.current,
                auth_header="Authorization",
                auth_prefix="Bearer ",
            )
        self.orders = UpstoxOrdersAdapter(self.transport, self.wire)
        self.market_data = UpstoxMarketDataAdapter(self.transport, self.wire)
        self.portfolio = UpstoxPortfolioAdapter(self.transport, self.wire, config=self.config)
        self.instruments = UpstoxInstrumentAdapter(self.transport, self.wire)
        self.streaming = UpstoxStreamingAdapter(
            wire=self.wire,
            ws_url=self.config.ws_url,
            token_provider=self._tokens.current,
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
            if not self._authenticated:
                return False
            try:
                self.portfolio.get_profile()
            except Exception as exc:
                msg = str(exc)
                # Cloudflare / WAF blocks are not fixed by TOTP
                if "1010" in msg or "error code: 1010" in msg:
                    raise
                if "401" in msg or "Unauthorized" in msg or "UDAPI100050" in msg:
                    if self.config.has_totp or self.config.refresh_token:
                        # Store/env may look unexpired but broker already revoked it
                        self._tokens.ensure_token(force_refresh=True)
                        self.portfolio.get_profile()
                    else:
                        raise
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
