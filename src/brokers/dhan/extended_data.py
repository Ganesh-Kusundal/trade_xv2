"""Dhan data capabilities — option chain, futures, expiries, alerts, validation.

Extracted from ``extended.py`` to keep the broker-specific surface focused.
This module must NOT import from ``extended.py`` to avoid circular deps.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from domain.symbols import normalize_exchange, normalize_symbol

if TYPE_CHECKING:
    from brokers.dhan.streaming.connection import DhanConnection


class DhanDataCapabilities:
    """Option chain, futures, expiries, alerts, and order validation."""

    def __init__(self, conn: DhanConnection) -> None:
        self._conn = conn

    def get_expiries(self, underlying: str, exchange: str = "NFO") -> list[str]:
        """Alias for get_option_expiries — used by contract suite."""
        return self.get_option_expiries(underlying, exchange)

    # ── Options (broker-specific) ────────────────────────────────────

    def get_option_expiries(self, underlying: str, exchange: str = "NFO") -> list[str]:
        """Get available option expiry dates."""
        return self._conn.options.get_expiries(underlying, exchange)

    def get_expired_options_data(
        self,
        security_id: int,
        expiry_flag: str,
        expiry_code: int,
        strike: str,
        option_type: str,
        from_date: str,
        to_date: str,
        required_data: list[str] | None = None,
        interval: int = 1,
    ) -> dict:
        """Fetch expired options OHLCV data from Dhan rolling option API."""
        return self._conn.options.get_expired_options_data(
            security_id=security_id,
            expiry_flag=expiry_flag,
            expiry_code=expiry_code,
            strike=strike,
            option_type=option_type,
            from_date=from_date,
            to_date=to_date,
            required_data=required_data,
            interval=interval,
        )

    def get_option_chain(
        self,
        underlying: str,
        exchange: str = "NFO",
        expiry: str | None = None,
    ) -> dict:
        """Get option chain with MCX-specific expiry lookup.

        For MCX underlyings, resolves the nearest futures contract to find the
        security ID, then uses the Dhan optionchain/expirylist endpoint directly.
        For NFO/BFO, delegates to the standard options adapter.
        """
        from brokers.dhan.segments import EXCHANGE_TO_SEGMENT

        mcx_underlyings = {
            "CRUDEOIL",
            "CRUDEOILM",
            "GOLD",
            "SILVER",
            "COPPER",
            "ZINC",
            "NATURALGAS",
            "ALUMINIUM",
            "LEAD",
            "NIKKEI",
        }
        sec_id = None
        seg = None
        if normalize_symbol(underlying) in mcx_underlyings and normalize_exchange(exchange) == "MCX":
            seg = EXCHANGE_TO_SEGMENT.get("MCX", "MCX_COMM")
            futures = [
                i
                for i in self._conn.instruments.all_instruments()
                if i.symbol.upper().startswith(normalize_symbol(underlying) + "-")
                and i.exchange.value == "MCX"
                and i.is_future
            ]
            futures.sort(key=lambda x: x.expiry or "")
            if futures:
                sec_id = int(futures[0].security_id)
        if expiry is None:
            if sec_id and seg:
                response = self._conn.client.post(
                    "/optionchain/expirylist",
                    json={
                        "UnderlyingScrip": sec_id,
                        "UnderlyingSeg": seg,
                    },
                )
                raw = response.get("data", response)
                if isinstance(raw, dict):
                    expiries = raw.get("expiryList") or raw.get("expiries") or []
                elif isinstance(raw, list):
                    expiries = raw
                else:
                    expiries = []
            else:
                expiries = self._conn.options.get_expiries(underlying, exchange)
            if not expiries:
                raise ValueError(f"No expiries found for {underlying}")
            expiry = expiries[0]
        if sec_id and seg:
            return self._conn.options.get_option_chain(
                underlying, exchange, expiry, security_id=sec_id
            )
        return self._conn.options.get_option_chain(underlying, exchange, expiry)

    # ── Futures (broker-specific) ────────────────────────────────────

    def get_futures_contracts(self, underlying: str, exchange: str = "NFO") -> list[dict]:
        """Get futures contracts for an underlying."""
        return self._conn.futures.get_contracts(underlying, exchange)

    def get_futures_expiries(self, underlying: str, exchange: str = "NFO") -> list[str]:
        """Get available futures expiry dates."""
        return self._conn.futures.get_expiries(underlying, exchange)

    def is_commodity(self, symbol: str) -> bool:
        """Check if a symbol is a commodity futures contract."""
        return self._conn.futures.is_commodity(symbol)

    # ── Order Validation ──────────────────────────────────────────────

    def validate_order(self, **kwargs: Any) -> list[str]:
        """Validate an order before placing. Returns list of errors (empty = valid)."""
        return self._conn.orders.validate_order(**kwargs)

    # ── Alerts ────────────────────────────────────────────────────────

    def get_alerts(self) -> list[Any]:
        """Get all alerts."""
        return self._conn.alerts.get_alerts() if hasattr(self._conn.alerts, "get_alerts") else []
