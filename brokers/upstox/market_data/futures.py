"""Upstox futures client (uses expired-instrument + option-contracts endpoints)."""

from __future__ import annotations

from typing import Any

from brokers.upstox.auth.urls import UpstoxApiUrlResolver


class UpstoxFuturesClient:
    def __init__(self, http_client: Any, url_resolver: UpstoxApiUrlResolver) -> None:
        self._http = http_client
        self._urls = url_resolver

    def get_contracts(self, underlying: str) -> list[dict[str, Any]]:
        body = self._http.get_json(
            self._urls.expired_future_contracts_url(),
            params={"instrument_key": underlying},
        )
        return _data_list(body)

    def get_nearest_contract(self, underlying: str) -> dict[str, Any]:
        contracts = self.get_contracts(underlying)
        return contracts[0] if contracts else {}

    def get_expiries(self, underlying: str) -> list[str]:
        body = self._http.get_json(
            self._urls.expired_expiries_url(),
            params={"instrument_key": underlying},
        )
        if isinstance(body, list):
            return [str(x) for x in body]
        data = body.get("data") if isinstance(body, dict) else None
        return [str(x) for x in data] if isinstance(data, list) else []

    def is_commodity(self, underlying: str) -> bool:
        return underlying.upper() in ("GOLD", "SILVER", "CRUDE", "CRUDEOIL", "NATURALGAS")


def _data_list(body: Any) -> list[dict[str, Any]]:
    if not isinstance(body, dict):
        return []
    data = body.get("data")
    return data if isinstance(data, list) else []
