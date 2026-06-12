"""Upstox options REST client (contracts, chain, greeks, expiries)."""

from __future__ import annotations

from typing import Any

from brokers.upstox.auth.urls import UpstoxApiUrlResolver


class UpstoxOptionsClient:
    def __init__(self, http_client: Any, url_resolver: UpstoxApiUrlResolver) -> None:
        self._http = http_client
        self._urls = url_resolver

    def get_contracts(
        self,
        instrument_key: str,
        expiry: str | None = None,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {"instrument_key": instrument_key}
        if expiry:
            params["expiry_date"] = expiry
        return self._http.get_json(self._urls.option_contracts_url(), params=params)

    def get_chain(
        self,
        instrument_key: str,
        expiry: str,
    ) -> dict[str, Any]:
        params = {
            "instrument_key": instrument_key,
            "expiry_date": expiry,
        }
        return self._http.get_json(self._urls.option_chain_url(), params=params)

    def get_expiries(
        self,
        instrument_key: str,
    ) -> list[str]:
        params = {"instrument_key": instrument_key}
        body = self._http.get_json(self._urls.option_expiry_url(), params=params)
        if not isinstance(body, list):
            data = body.get("data") if isinstance(body, dict) else None
            if isinstance(data, list):
                return [str(x) for x in data]
            return []
        return [str(x) for x in body]

    def get_greeks(self, instrument_keys: list[str]) -> dict[str, Any]:
        if isinstance(instrument_keys, str):
            instrument_keys = [instrument_keys]
        params = {"instrument_key": ",".join(instrument_keys)}
        return self._http.get_json(self._urls.option_greeks_url(), params=params)
